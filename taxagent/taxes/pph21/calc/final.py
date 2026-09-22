from __future__ import annotations

from decimal import Decimal

from .models import FinalIncomeType, PPh21Result
from .rates import calc_progressive, load_rates
from .rounding import money, round_rupiah

VALID_GRADES = ("I", "II", "III", "IV")


def calc_final(
    jenis: FinalIncomeType,
    jumlah_bruto,
    tahun: int,
    golongan: str | None = None,
    masa_pajak: int | None = None,
) -> PPh21Result:
    table = load_rates(tahun)
    gross = money(jumlah_bruto)
    if gross < 0:
        raise ValueError("jumlah bruto tidak boleh negatif")

    result = PPh21Result(
        jenis_perhitungan=f"final_{jenis.value}",
        tahun_pajak=tahun,
        masa_pajak=masa_pajak,
        penghasilan_bruto=gross,
        dasar_pengenaan_pajak=gross,
    )
    result.peringatan.extend(table.verification_warning())
    result.add_step("Jumlah bruto", gross)

    if jenis is FinalIncomeType.HONORARIUM_PNS:
        if golongan is None:
            raise ValueError("honorarium PNS membutuhkan golongan (I, II, III, atau IV)")
        grade = golongan.strip().upper()
        if grade not in VALID_GRADES:
            raise ValueError(f"golongan '{golongan}' tidak valid; pilih {', '.join(VALID_GRADES)}")
        rate = money(table.final_honorarium_pns[grade])
        pph = gross * rate / Decimal(100)
        result.metode_tarif = f"PPh final {rate}% (Golongan {grade})"
        result.add_step(f"Tarif final Golongan {grade}", catatan=f"{rate}%")
        result.add_step("PPh final", pph, formula=f"{gross} x {rate}%")
        result.dasar_hukum.append("PP No. 80 Tahun 2010 Pasal 4 ayat (2)")
        result.pph_sebelum_penalti = round_rupiah(pph)
        result.pph_terutang = result.pph_sebelum_penalti
        return result

    if jenis is FinalIncomeType.PESANGON:
        brackets = table.final_pesangon
        result.dasar_hukum.extend(["PP No. 68 Tahun 2009 Pasal 4 dan Pasal 2 ayat (2)", "PMK No. 16/PMK.03/2010"])
        result.asumsi.append(
            "Dianggap dibayarkan sekaligus, yaitu paling lama 2 tahun kalender. "
            "Bagian yang dibayar pada tahun ketiga dan seterusnya tidak bersifat final dan "
            "dikenakan tarif Pasal 17 (tahun_pembayaran_ke=3)."
        )
    else:
        brackets = table.final_manfaat_pensiun
        result.dasar_hukum.append("PP No. 68 Tahun 2009 Pasal 5")

    result.metode_tarif = "PPh final berlapis"
    pph, breakdown = calc_progressive(gross, brackets)
    for bracket, taxed, tax in breakdown:
        result.add_step(f"Lapisan {bracket.persen}%", tax, formula=f"{taxed} x {bracket.persen}%")
    result.add_step("PPh final", pph)

    result.pph_sebelum_penalti = round_rupiah(pph)
    result.pph_terutang = result.pph_sebelum_penalti
    return result


def calc_lump_sum_third_year(
    jenis: FinalIncomeType,
    jumlah_bruto,
    tahun: int,
    punya_npwp: bool = True,
    dibayar_sebelumnya_tahun_ini=0,
    masa_pajak: int | None = None,
) -> PPh21Result:
    if jenis is FinalIncomeType.HONORARIUM_PNS:
        raise ValueError("tahun pembayaran ketiga hanya untuk pesangon atau manfaat_pensiun (termasuk THT/JHT)")
    table = load_rates(tahun)
    gross = money(jumlah_bruto)
    earlier = money(dibayar_sebelumnya_tahun_ini)
    if gross < 0 or earlier < 0:
        raise ValueError("jumlah bruto tidak boleh negatif")

    result = PPh21Result(
        jenis_perhitungan=f"tahun_ketiga_{jenis.value}",
        tahun_pajak=tahun,
        masa_pajak=masa_pajak,
        penghasilan_bruto=gross,
        dasar_pengenaan_pajak=gross + earlier,
        metode_tarif="Tarif Pasal 17 atas bruto kumulatif tahun kalender (tidak final)",
    )
    result.peringatan.extend(table.verification_warning())
    result.dasar_hukum.extend(["PP No. 68 Tahun 2009 Pasal 6", "PMK No. 16/PMK.03/2010 Pasal 5"])
    result.add_step("Jumlah bruto pembayaran ini", gross)
    pph, breakdown = calc_progressive(gross + earlier, table.tarif_pasal_17)
    if earlier:
        result.add_step("Dibayar sebelumnya pada tahun kalender ini", earlier)
        result.add_step("Jumlah bruto kumulatif tahun kalender ini", gross + earlier)
    for bracket, taxed, tax in breakdown:
        result.add_step(f"Lapisan {bracket.persen}%", tax, formula=f"{taxed} x {bracket.persen}%")
    if earlier:
        earlier_pph, _ = calc_progressive(earlier, table.tarif_pasal_17)
        result.add_step("PPh atas pembayaran sebelumnya", earlier_pph)
        pph = pph - earlier_pph
    result.add_step("PPh 21 (tidak final)", pph)
    result.asumsi.append(
        "Bagian yang dibayar pada tahun kalender ketiga sejak pembayaran pertama. PPh ini tidak final dan "
        "dapat dikreditkan di SPT Tahunan penerima."
    )

    result.pph_sebelum_penalti = round_rupiah(pph)
    if punya_npwp:
        result.pph_terutang = result.pph_sebelum_penalti
    else:
        total = round_rupiah(pph * table.faktor_non_npwp)
        result.penalti_non_npwp = total - result.pph_sebelum_penalti
        result.pph_terutang = total
        result.add_step("Tarif lebih tinggi karena tidak ber-NPWP", total)
        result.dasar_hukum.append("PMK No. 16/PMK.03/2010 Pasal 5 ayat (3)")
    return result
