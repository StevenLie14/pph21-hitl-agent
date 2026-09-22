from decimal import Decimal

import pytest

from taxagent.taxes.pph21.calc import (
    IncomeComponents,
    PTKPStatus,
    calc_annual,
    calc_final_period,
    calc_monthly_ter,
    parse_ptkp_status,
)

TAHUN = 2025
BRUTO_UJI = [0, 4_000_000, 6_000_000, 10_000_000, 25_000_000, 80_000_000, 500_000_000]


def _k(bruto: int) -> IncomeComponents:
    return IncomeComponents(gaji_pokok=bruto)


@pytest.mark.parametrize("bruto", BRUTO_UJI)
@pytest.mark.parametrize("status", list(PTKPStatus))
def test_pph_never_negative(bruto, status):
    h = calc_monthly_ter(_k(bruto), status, TAHUN, 1)
    assert h.pph_terutang >= 0
    t = calc_annual(_k(bruto * 12), status, TAHUN)
    assert t.pph_terutang >= 0


@pytest.mark.parametrize("bruto", BRUTO_UJI)
def test_adding_dependants_does_not_raise_tax(bruto):
    urut = [PTKPStatus.K0, PTKPStatus.K1, PTKPStatus.K2, PTKPStatus.K3]
    tahunan = [calc_annual(_k(bruto * 12), s, TAHUN).pph_terutang for s in urut]
    assert tahunan == sorted(tahunan, reverse=True)

    bulanan = [calc_monthly_ter(_k(bruto), s, TAHUN, 1).pph_terutang for s in urut]
    assert bulanan == sorted(bulanan, reverse=True)


@pytest.mark.parametrize("status", list(PTKPStatus))
def test_tax_rises_with_income(status):
    hasil = [calc_annual(_k(b * 12), status, TAHUN).pph_terutang for b in BRUTO_UJI]
    assert hasil == sorted(hasil)


@pytest.mark.parametrize("bruto", BRUTO_UJI)
@pytest.mark.parametrize("status", list(PTKPStatus))
def test_income_below_ptkp_not_taxed(bruto, status):
    from taxagent.taxes.pph21.calc import annual_ptkp

    setahun = bruto * 12
    if setahun >= annual_ptkp(status, TAHUN):
        pytest.skip("penghasilan di atas PTKP")
    assert calc_annual(_k(setahun), status, TAHUN).pph_terutang == 0


@pytest.mark.parametrize("bruto", [10_000_000, 25_000_000, 80_000_000])
@pytest.mark.parametrize("status", list(PTKPStatus))
def test_period_accumulation_equals_annual(bruto, status):
    komponen = _k(bruto)
    jan_nov = sum(
        (calc_monthly_ter(komponen, status, TAHUN, m).pph_terutang for m in range(1, 12)),
        Decimal(0),
    )
    desember = calc_final_period(
        komponen.scaled(12), status, TAHUN, jan_nov
    )
    setahun = calc_annual(komponen.scaled(12), status, TAHUN)
    assert jan_nov + desember.pph_terutang == setahun.pph_terutang


@pytest.mark.parametrize("bruto", [10_000_000, 25_000_000])
def test_non_npwp_always_20_percent_higher(bruto):
    status = parse_ptkp_status("TK/0")
    dengan = calc_monthly_ter(_k(bruto), status, TAHUN, 1, punya_npwp=True)
    tanpa = calc_monthly_ter(_k(bruto), status, TAHUN, 1, punya_npwp=False)
    assert tanpa.pph_terutang == dengan.pph_terutang * Decimal("1.2")
    assert tanpa.penalti_non_npwp == tanpa.pph_terutang - tanpa.pph_sebelum_penalti


def test_over_withholding_reported_as_warning():
    status = parse_ptkp_status("TK/0")
    h = calc_final_period(_k(120_000_000), status, TAHUN, 99_000_000)
    assert h.pph_terutang < 0
    assert any("kelebihan potong" in p.lower() for p in h.peringatan)


def test_negative_component_rejected():
    with pytest.raises(ValueError):
        IncomeComponents(gaji_pokok=-1)


def test_biaya_jabatan_capped():
    h = calc_annual(_k(10_000_000_000), PTKPStatus.TK0, TAHUN)
    baris = next(l for l in h.langkah if l.label == "Biaya jabatan")
    assert baris.nilai == Decimal(6_000_000)


def test_biaya_jabatan_prorated_for_partial_earning_period():
    h = calc_annual(_k(120_000_000), PTKPStatus.TK0, TAHUN, bulan_masa_perolehan=3)
    baris = next(l for l in h.langkah if l.label == "Biaya jabatan")
    assert baris.nilai == Decimal(1_500_000)
