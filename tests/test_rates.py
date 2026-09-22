from decimal import Decimal

import pytest

from taxagent.taxes.pph21.calc import TERCategory, available_years, load_rates
from taxagent.taxes.pph21.calc.rates import TaxYearNotAvailable, calc_progressive

TAHUN = 2025


def test_available_years_exist():
    assert available_years(), "harus ada minimal satu berkas tarif"


def test_missing_year_fails_hard():
    with pytest.raises(TaxYearNotAvailable):
        load_rates(1999)


def test_inheritance_across_years():
    a, b = load_rates(2024), load_rates(2025)
    assert b.tahun_pajak == 2025
    assert b.annual_ptkp.__self__ is b
    assert len(b._ter_bulanan["A"]) == len(a._ter_bulanan["A"])


@pytest.mark.parametrize("kategori", ["A", "B", "C"])
def test_monthly_ter_monotonic(kategori):
    tabel = load_rates(TAHUN)
    lapisan = tabel._ter_bulanan[kategori]

    assert lapisan[-1].batas_atas is None, "lapisan terakhir harus terbuka ke atas"
    for lap in lapisan[:-1]:
        assert lap.batas_atas is not None, "hanya lapisan terakhir yang boleh terbuka"

    batas = [l.batas_atas for l in lapisan[:-1]]
    assert batas == sorted(batas), "batas atas harus menaik"
    assert len(set(batas)) == len(batas), "ada batas atas yang duplikat"

    tarif = [l.persen for l in lapisan]
    assert tarif == sorted(tarif), "tarif efektif harus tidak menurun"
    assert tarif[0] == Decimal(0), "bracket terendah harus 0%"


@pytest.mark.parametrize("kategori", ["A", "B", "C"])
def test_ter_has_no_gaps(kategori):
    tabel = load_rates(TAHUN)
    kat = TERCategory(kategori)
    lapisan = tabel._ter_bulanan[kategori]

    for lap in lapisan[:-1]:
        di_batas = tabel.monthly_ter_rate(kat, lap.batas_atas)
        assert di_batas.persen == lap.persen, (
            "nilai persis di batas atas harus masuk bracket itu, bukan berikutnya"
        )
        setelah = tabel.monthly_ter_rate(kat, lap.batas_atas + Decimal(1))
        assert setelah.persen > lap.persen


def test_tax_free_threshold_rises_from_a_to_c():
    tabel = load_rates(TAHUN)
    ambang = [tabel._ter_bulanan[k][0].batas_atas for k in ("A", "B", "C")]
    assert ambang == sorted(ambang) and len(set(ambang)) == 3


def test_ter_category_follows_ptkp_order():
    from taxagent.taxes.pph21.calc.models import PTKPStatus

    tabel = load_rates(TAHUN)
    urut = {"A": 0, "B": 1, "C": 2}
    pasangan = sorted(
        ((tabel.annual_ptkp(s), urut[tabel.ter_category(s).value]) for s in PTKPStatus),
        key=lambda x: x[0],
    )
    kategori = [k for _, k in pasangan]
    assert kategori == sorted(kategori), "PTKP lebih besar tidak boleh masuk kategori lebih rendah"


def test_pasal_17_rate_brackets():
    tabel = load_rates(TAHUN)
    lapisan = tabel.tarif_pasal_17
    assert [l.persen for l in lapisan] == [Decimal(x) for x in (5, 15, 25, 30, 35)]
    assert lapisan[-1].batas_atas is None


@pytest.mark.parametrize(
    "pkp,harapan",
    [
        (0, 0),
        (60_000_000, 3_000_000),
        (123_000_000, 12_450_000),
        (250_000_000, 31_500_000),
        (500_000_000, 94_000_000),
    ],
)
def test_progressive(pkp, harapan):
    tabel = load_rates(TAHUN)
    total, _ = calc_progressive(Decimal(pkp), tabel.tarif_pasal_17)
    assert total == Decimal(harapan)


def test_provenance_warning_appears_when_unverified():
    tabel = load_rates(TAHUN)
    if tabel.terverifikasi:
        pytest.skip("tabel sudah ditandai terverifikasi")
    assert tabel.verification_warning(), (
        "tabel yang belum diverifikasi wajib memancarkan peringatan"
    )
