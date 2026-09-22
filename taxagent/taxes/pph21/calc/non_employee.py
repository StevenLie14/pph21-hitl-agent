from __future__ import annotations

from decimal import Decimal

from .models import PPh21Result
from .rates import calc_progressive, load_rates
from .rounding import money, round_rupiah

ZERO = Decimal(0)


def calc_non_employee(
    bruto,
    tahun: int,
    punya_npwp: bool = True,
    pembayaran_dikecualikan=0,
    jasa_katering: bool = False,
    masa_pajak: int | None = None,
) -> PPh21Result:
    table = load_rates(tahun)
    received = money(bruto)
    excluded = money(pembayaran_dikecualikan)
    if received < 0 or excluded < 0:
        raise ValueError("penghasilan bruto dan pembayaran dikecualikan tidak boleh negatif")
    catering_warning = None
    if excluded > 0 and jasa_katering:
        catering_warning = (
            f"Pembayaran dikecualikan {excluded} DIABAIKAN: untuk jasa katering, penghasilan "
            "bruto adalah seluruh jumlah yang diterima (PMK 168/2023 Pasal 12 ayat (4) huruf a)."
        )
        excluded = ZERO
    if excluded > received:
        raise ValueError("pembayaran dikecualikan tidak boleh melebihi jumlah yang diterima")

    base_gross = received - excluded
    result = PPh21Result(
        jenis_perhitungan="bukan_pegawai",
        tahun_pajak=tahun,
        masa_pajak=masa_pajak,
        penghasilan_bruto=base_gross,
        metode_tarif="Tarif Pasal 17 atas DPP masa pajak ini",
    )
    result.peringatan.extend(table.verification_warning())
    result.dasar_hukum.append("PMK No. 168 Tahun 2023 Pasal 12 ayat (3) dan Pasal 16 ayat (3)")
    if catering_warning:
        result.peringatan.append(catering_warning)
        result.dasar_hukum.append("PMK No. 168 Tahun 2023 Pasal 12 ayat (4) huruf a")

    if excluded > 0:
        result.add_step("Jumlah yang diterima", received)
        result.add_step(
            "Pembayaran upah tenaga kerja/material/pihak ketiga",
            excluded,
            catatan="Dikecualikan dari bruto sepanjang dibuktikan dengan kontrak dan faktur.",
        )
        result.add_step("Penghasilan bruto", base_gross, formula=f"{received} - {excluded}")
        result.dasar_hukum.append("PMK No. 168 Tahun 2023 Pasal 12 ayat (4) huruf b dan ayat (5)")
        result.asumsi.append(
            "Pembayaran yang dikecualikan dapat dibuktikan dengan kontrak kerja/daftar "
            "upah, faktur pembelian material, atau faktur tagihan pihak ketiga."
        )
    else:
        result.add_step("Penghasilan bruto", base_gross)

    base_rate = money(table.bukan_pegawai["dpp_persen"])
    base = base_gross * base_rate / Decimal(100)
    result.add_step("Dasar pengenaan pajak", base, formula=f"{base_rate}% x {base_gross}")
    result.dasar_pengenaan_pajak = base

    pph, breakdown = calc_progressive(base, table.tarif_pasal_17)
    for bracket, taxed, tax in breakdown:
        result.add_step(f"Lapisan {bracket.persen}%", tax, formula=f"{taxed} x {bracket.persen}%")
    result.add_step(
        "PPh 21 masa ini",
        pph,
        formula=f"Pasal 17 atas DPP masa pajak ini ({base}), tidak kumulatif",
    )

    result.pph_sebelum_penalti = round_rupiah(pph)
    if punya_npwp:
        result.pph_terutang = result.pph_sebelum_penalti
    else:
        total = round_rupiah(pph * table.faktor_non_npwp)
        result.penalti_non_npwp = total - result.pph_sebelum_penalti
        result.pph_terutang = total
        result.add_step("Tarif lebih tinggi karena tidak ber-NPWP", total)
        result.dasar_hukum.append("UU PPh Pasal 21 ayat (5a)")

    return result
