from __future__ import annotations

from decimal import Decimal

from .models import PPh21Result, PTKPStatus
from .permanent_employee import apply_non_npwp
from .ptkp import ptkp_breakdown
from .rates import calc_progressive, load_rates
from .rounding import format_rupiah, money, round_down, round_rupiah

ZERO = Decimal(0)


def _gross_breakdown(pension: Decimal, other_income: Decimal) -> str:
    parts = [f"uang pensiun {pension}"]
    if other_income:
        parts.append(f"penghasilan lain {other_income}")
    return " + ".join(parts)


def _check_non_negative(**values: Decimal) -> None:
    for name, v in values.items():
        if v < 0:
            raise ValueError(f"{name} tidak boleh negatif")


def calc_pensioner_monthly_ter(
    uang_pensiun: Decimal | int | float,
    status: PTKPStatus,
    tahun: int,
    masa_pajak: int,
    penghasilan_lain: Decimal | int | float = 0,
    punya_npwp: bool = True,
) -> PPh21Result:
    if not 1 <= masa_pajak <= 12:
        raise ValueError("masa_pajak harus 1 sampai 12")
    pension, other = money(uang_pensiun), money(penghasilan_lain)
    _check_non_negative(uang_pensiun=pension, penghasilan_lain=other)

    table = load_rates(tahun)
    gross = pension + other
    category = table.ter_category(status)
    bracket = table.monthly_ter_rate(category, gross)

    result = PPh21Result(
        jenis_perhitungan="pensiunan_bulanan_ter",
        tahun_pajak=tahun,
        masa_pajak=masa_pajak,
        penghasilan_bruto=gross,
        dasar_pengenaan_pajak=gross,
        metode_tarif=f"TER kategori {category.value}, tarif {bracket.persen}%",
    )
    result.peringatan.extend(table.verification_warning())

    result.add_step("Penghasilan bruto sebulan", gross, formula=_gross_breakdown(pension, other))
    result.add_step(
        f"Status PTKP {status.value} masuk kategori TER {category.value}",
        catatan="Kategori TER ditentukan status PTKP, bukan besaran penghasilan.",
    )
    upper = "tak terbatas" if bracket.batas_atas is None else format_rupiah(bracket.batas_atas)
    result.add_step(
        f"Tarif efektif bulanan {bracket.persen}%",
        catatan=f"Bracket penghasilan bruto sampai dengan {upper}.",
    )

    pph = gross * bracket.persen / Decimal(100)
    result.add_step("PPh 21 masa (sebelum penyesuaian)", pph, formula=f"{gross} x {bracket.persen}%")
    apply_non_npwp(result, pph, table, punya_npwp)

    result.dasar_hukum.extend(["PP No. 58 Tahun 2023", "PMK No. 168 Tahun 2023 Pasal 15 ayat (1)"])
    result.asumsi.append(
        "Metode TER dipakai untuk masa pajak selain masa pajak terakhir. Biaya "
        "pensiun dan zakat tidak diperhitungkan di sini, melainkan pada "
        "perhitungan ulang masa pajak terakhir."
    )
    if masa_pajak == 12:
        result.peringatan.append(
            "Masa pajak 12 (Desember) umumnya merupakan masa pajak terakhir dan "
            "harus dihitung ulang dengan tarif Pasal 17, bukan dengan TER. "
            "Gunakan perhitungan masa pajak terakhir pensiunan."
        )
    return result


def calc_pensioner_annual(
    uang_pensiun_setahun: Decimal | int | float,
    status: PTKPStatus,
    tahun: int,
    penghasilan_lain_setahun: Decimal | int | float = 0,
    zakat_setahun: Decimal | int | float = 0,
    punya_npwp: bool = True,
    bulan_masa_perolehan: int = 12,
    disetahunkan: bool = False,
    neto_pemberi_sebelumnya: Decimal | int | float = 0,
) -> PPh21Result:
    if not 1 <= bulan_masa_perolehan <= 12:
        raise ValueError("bulan_masa_perolehan harus 1 sampai 12")
    pension = money(uang_pensiun_setahun)
    other = money(penghasilan_lain_setahun)
    zakat = money(zakat_setahun)
    previous_net = money(neto_pemberi_sebelumnya)
    _check_non_negative(
        uang_pensiun=pension, penghasilan_lain=other, zakat=zakat,
        neto_pemberi_sebelumnya=previous_net,
    )

    table = load_rates(tahun)
    gross = pension + other
    if gross == 0 and previous_net > 0:
        raise ValueError(
            "uang pensiun dari pembayar ini nol padahal neto_pemberi_sebelumnya diisi. Field itu "
            "HANYA untuk neto dari bukti potong pemberi kerja/pembayar LAIN; uang pensiun dari "
            "pembayar ini masuk ke uang_pensiun"
        )

    result = PPh21Result(
        jenis_perhitungan="pensiunan_tahunan",
        tahun_pajak=tahun,
        penghasilan_bruto=gross,
        metode_tarif="Tarif Pasal 17 UU HPP",
    )
    result.peringatan.extend(table.verification_warning())
    result.add_step("Penghasilan bruto (pembayar pensiun ini)", gross, formula=_gross_breakdown(pension, other))

    expense_rate = money(table.biaya_pensiun["persen"])
    expense_computed = gross * expense_rate / Decimal(100)
    expense_cap = min(
        money(table.biaya_pensiun["maksimal_sebulan"]) * bulan_masa_perolehan,
        money(table.biaya_pensiun["maksimal_setahun"]),
    )
    pension_expense = min(expense_computed, expense_cap)
    result.add_step(
        "Biaya pensiun",
        pension_expense,
        formula=f"min({expense_rate}% x {gross} = {expense_computed}, batas {expense_cap})",
        catatan="Paling banyak Rp200.000 sebulan atau Rp2.400.000 setahun.",
    )
    if zakat > 0:
        result.add_step(
            "Zakat/sumbangan keagamaan wajib melalui pembayar pensiun",
            zakat,
        )

    net = gross - pension_expense - zakat
    net_formula = f"{gross} - {pension_expense} - {zakat}"
    if previous_net > 0:
        result.add_step("Penghasilan neto (pembayar pensiun ini)", net, formula=net_formula)
        result.add_step(
            "Penghasilan neto pemberi kerja/pembayar sebelumnya",
            previous_net,
            catatan="Dari bukti pemotongan pemberi kerja/pembayar sebelumnya di tahun pajak yang sama.",
        )
        this_net = net
        net = this_net + previous_net
        result.add_step("Penghasilan neto setahun", net, formula=f"{this_net} + {previous_net}")
        result.asumsi.append(
            "Penghasilan neto dari pemberi kerja/pembayar sebelumnya di tahun pajak "
            "yang sama digabung sebelum PTKP dan tarif Pasal 17 diterapkan."
        )
    else:
        result.add_step("Penghasilan neto setahun", net, formula=net_formula)

    base_net = net
    if disetahunkan and bulan_masa_perolehan < 12:
        base_net = net * Decimal(12) / Decimal(bulan_masa_perolehan)
        result.add_step(
            "Penghasilan neto disetahunkan",
            base_net,
            formula=f"{net} x 12 / {bulan_masa_perolehan}",
        )

    ptkp = table.annual_ptkp(status)
    result.add_step(f"PTKP {status.value}", ptkp, formula=" + ".join(ptkp_breakdown(status, table)))

    raw_pkp = max(base_net - ptkp, ZERO)
    pkp = round_down(raw_pkp, table.pembulatan_pkp)
    result.add_step(
        "Penghasilan Kena Pajak",
        pkp,
        formula=f"max({base_net} - {ptkp}, 0) dibulatkan ke bawah kelipatan {table.pembulatan_pkp}",
    )
    result.dasar_pengenaan_pajak = pkp

    pph, breakdown = calc_progressive(pkp, table.tarif_pasal_17)
    for bracket, taxed, tax in breakdown:
        result.add_step(f"Lapisan {bracket.persen}%", tax, formula=f"{taxed} x {bracket.persen}%")
    result.add_step("PPh 21 setahun (sebelum penyesuaian)", pph)

    if disetahunkan and bulan_masa_perolehan < 12:
        pph = pph * Decimal(bulan_masa_perolehan) / Decimal(12)
        result.add_step(
            "PPh 21 sesuai masa perolehan",
            pph,
            formula=f"PPh disetahunkan x {bulan_masa_perolehan} / 12",
        )

    apply_non_npwp(result, pph, table, punya_npwp)

    result.dasar_hukum.extend(
        [
            "UU PPh Pasal 17 ayat (1) huruf a s.t.d.t.d UU HPP",
            "UU PPh Pasal 7 ayat (1)",
            "PMK No. 168 Tahun 2023 Pasal 11 ayat (1) dan (2)",
            "PMK No. 168 Tahun 2023 Pasal 15 ayat (1)",
        ]
    )
    if previous_net > 0:
        result.dasar_hukum.append("PMK No. 168 Tahun 2023 Pasal 11 ayat (3)")
    if bulan_masa_perolehan < 12:
        result.asumsi.append(
            f"Uang pensiun diterima {bulan_masa_perolehan} bulan dari pembayar ini"
            + (", penghasilan neto disetahunkan." if disetahunkan else ", tanpa disetahunkan.")
        )
    return result


def calc_pensioner_final_period(
    uang_pensiun_setahun: Decimal | int | float,
    status: PTKPStatus,
    tahun: int,
    pph_sudah_dipotong: Decimal | int | float,
    penghasilan_lain_setahun: Decimal | int | float = 0,
    zakat_setahun: Decimal | int | float = 0,
    punya_npwp: bool = True,
    masa_pajak: int = 12,
    bulan_masa_perolehan: int = 12,
    disetahunkan: bool = False,
    neto_pemberi_sebelumnya: Decimal | int | float = 0,
    pph_dipotong_pemberi_sebelumnya: Decimal | int | float = 0,
) -> PPh21Result:
    annual = calc_pensioner_annual(
        uang_pensiun_setahun,
        status,
        tahun,
        penghasilan_lain_setahun=penghasilan_lain_setahun,
        zakat_setahun=zakat_setahun,
        punya_npwp=punya_npwp,
        bulan_masa_perolehan=bulan_masa_perolehan,
        disetahunkan=disetahunkan,
        neto_pemberi_sebelumnya=neto_pemberi_sebelumnya,
    )

    withheld_here = money(pph_sudah_dipotong)
    withheld_previous = money(pph_dipotong_pemberi_sebelumnya)
    withheld = withheld_here + withheld_previous
    difference = annual.pph_terutang - withheld

    result = PPh21Result(
        jenis_perhitungan="pensiunan_masa_pajak_terakhir",
        tahun_pajak=tahun,
        masa_pajak=masa_pajak,
        penghasilan_bruto=annual.penghasilan_bruto,
        dasar_pengenaan_pajak=annual.dasar_pengenaan_pajak,
        metode_tarif=annual.metode_tarif,
        langkah=list(annual.langkah),
        dasar_hukum=list(annual.dasar_hukum),
        asumsi=list(annual.asumsi),
        peringatan=list(annual.peringatan),
    )
    result.add_step("PPh 21 terutang setahun", annual.pph_terutang)
    if withheld_previous > 0:
        result.add_step(
            "PPh 21 terutang di pemberi kerja/pembayar sebelumnya",
            withheld_previous,
            catatan="Dari bukti pemotongan pemberi kerja/pembayar sebelumnya.",
        )
    result.add_step(
        "PPh 21 yang telah dipotong pembayar pensiun ini",
        withheld_here,
        catatan="Jumlah pemotongan masa-masa pajak sebelumnya di pembayar ini.",
    )
    result.add_step("PPh 21 masa pajak terakhir", difference, formula=f"{annual.pph_terutang} - {withheld}")

    result.pph_sebelum_penalti = annual.pph_sebelum_penalti
    result.penalti_non_npwp = annual.penalti_non_npwp
    result.pph_terutang = round_rupiah(difference) if difference >= 0 else -round_rupiah(-difference)

    if difference < 0:
        result.peringatan.append(
            f"Terjadi kelebihan potong sebesar {-difference}. Kelebihan ini "
            f"dikembalikan kepada pensiunan pada masa pajak terakhir."
        )
    result.dasar_hukum.append("PMK No. 168 Tahun 2023 Pasal 15 ayat (1) huruf b dan ayat (2)")
    return result
