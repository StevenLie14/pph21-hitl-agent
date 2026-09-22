from __future__ import annotations

from decimal import Decimal

from .models import PPh21Result, PTKPStatus, WageScheme
from .rates import RateTable, calc_progressive, load_rates
from .rounding import format_rupiah, money, round_rupiah

ZERO = Decimal(0)


def calc_non_permanent_employee(
    upah_per_periode,
    skema: WageScheme,
    tahun: int,
    jumlah_hari: int = 1,
    status: PTKPStatus | None = None,
    punya_npwp: bool = True,
    masa_pajak: int | None = None,
) -> PPh21Result:
    table = load_rates(tahun)
    wage = money(upah_per_periode)
    if wage < 0:
        raise ValueError("upah tidak boleh negatif")
    if jumlah_hari < 1:
        raise ValueError("jumlah_hari minimal 1")

    result = PPh21Result(
        jenis_perhitungan=f"pegawai_tidak_tetap_{skema.value}",
        tahun_pajak=tahun,
        masa_pajak=masa_pajak,
        penghasilan_bruto=wage,
    )
    result.peringatan.extend(table.verification_warning())
    result.dasar_hukum.extend(
        [
            "PP No. 58 Tahun 2023",
            "PMK No. 168 Tahun 2023 Pasal 12 ayat (2) dan Pasal 16 ayat (2)",
        ]
    )

    if skema is WageScheme.BULANAN:
        if status is None:
            raise ValueError("skema bulanan membutuhkan status PTKP untuk menentukan kategori TER")
        category = table.ter_category(status)
        bracket = table.monthly_ter_rate(category, wage)
        result.metode_tarif = f"TER bulanan kategori {category.value}, tarif {bracket.persen}%"
        result.dasar_pengenaan_pajak = wage
        result.add_step("Upah sebulan", wage)
        result.add_step(f"TER bulanan kategori {category.value}", catatan=f"tarif {bracket.persen}%")
        pph = wage * bracket.persen / Decimal(100)
        result.add_step("PPh 21", pph, formula=f"{wage} x {bracket.persen}%")
        _non_npwp(result, pph, table, punya_npwp)
        return result

    daily_wage = wage / Decimal(jumlah_hari)
    if jumlah_hari > 1:
        result.add_step(
            "Upah sehari",
            daily_wage,
            formula=f"{wage} / {jumlah_hari} hari",
        )

    daily_ter_limit = money(table.ter_harian["batas_atas_ter_harian"])

    if daily_wage > daily_ter_limit:
        base_rate = money(table.ter_harian["dpp_persen_di_atas_batas"])
        base = wage * base_rate / Decimal(100)
        result.metode_tarif = f"Tarif Pasal 17 atas {base_rate}% penghasilan bruto"
        result.dasar_pengenaan_pajak = base
        result.add_step(
            f"Upah sehari melebihi batas TER harian ({daily_ter_limit})",
            catatan="Dikenakan tarif Pasal 17 atas 50% penghasilan bruto.",
        )
        result.add_step("Dasar pengenaan pajak", base, formula=f"{base_rate}% x {wage}")
        pph, breakdown = calc_progressive(base, table.tarif_pasal_17)
        for bracket, taxed, tax in breakdown:
            result.add_step(f"Lapisan {bracket.persen}%", tax, formula=f"{taxed} x {bracket.persen}%")
        _non_npwp(result, pph, table, punya_npwp)
        return result

    bracket = table.daily_ter_rate(daily_wage)

    result.metode_tarif = f"TER harian {bracket.persen}%"
    result.dasar_pengenaan_pajak = wage
    result.add_step(
        f"Tarif efektif harian {bracket.persen}%",
        catatan=(
            f"Upah sehari {daily_wage} berada pada bracket sampai dengan "
            + ("tak terbatas" if bracket.batas_atas is None else format_rupiah(bracket.batas_atas))
            + "."
        ),
    )
    pph = wage * bracket.persen / Decimal(100)
    result.add_step("PPh 21", pph, formula=f"{wage} x {bracket.persen}%")
    _non_npwp(result, pph, table, punya_npwp)
    return result


def _non_npwp(result: PPh21Result, pph: Decimal, table: RateTable, punya_npwp: bool) -> None:
    result.pph_sebelum_penalti = round_rupiah(pph)
    if punya_npwp:
        result.pph_terutang = result.pph_sebelum_penalti
        return
    total = round_rupiah(pph * table.faktor_non_npwp)
    result.penalti_non_npwp = total - result.pph_sebelum_penalti
    result.pph_terutang = total
    result.add_step("Tarif lebih tinggi karena tidak ber-NPWP", total)
    result.dasar_hukum.append("UU PPh Pasal 21 ayat (5a)")
