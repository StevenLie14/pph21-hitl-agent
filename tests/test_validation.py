from __future__ import annotations

from decimal import Decimal

import pytest

from taxagent.taxes.pph21.calc import IncomeComponents, PTKPStatus, calc_monthly_ter_gross_up
from taxagent.tools import call_tool


def test_catering_ignores_excluded_payment_with_warning():
    hasil = call_tool(
        "calculate_pph21_non_employee",
        penghasilan_bruto=10_000_000,
        pembayaran_dikecualikan=2_000_000,
        jasa_katering=True,
        tahun_pajak=2024,
    )
    assert hasil["berhasil"]
    assert hasil["dasar_pengenaan_pajak"] == "5000000"
    assert any("katering" in p for p in hasil["peringatan"])


def test_previous_employer_net_without_this_employer_income_rejected():
    hasil = call_tool(
        "calculate_pph21_permanent_last_period",
        neto_pemberi_kerja_sebelumnya=140_000_000,
        status_ptkp="TK/0",
        pph_sudah_dipotong=0,
        tahun_pajak=2024,
    )
    assert not hasil["berhasil"]
    assert "gaji_pokok" in hasil["galat"]


def test_excluded_payment_cannot_exceed_gross():
    hasil = call_tool(
        "calculate_pph21_non_employee",
        penghasilan_bruto=1_000_000,
        pembayaran_dikecualikan=2_000_000,
        tahun_pajak=2024,
    )
    assert not hasil["berhasil"]


def test_gross_up_rejects_manual_pph_allowance():
    hasil = call_tool(
        "calculate_pph21_permanent_monthly",
        gaji_pokok=10_000_000,
        tunjangan_pph=500_000,
        gross_up=True,
        status_ptkp="TK/0",
        masa_pajak=1,
        tahun_pajak=2024,
    )
    assert not hasil["berhasil"]


def test_pensioner_rejects_negative_values():
    hasil = call_tool(
        "calculate_pph21_pensioner_annual",
        uang_pensiun=10_000_000,
        neto_pemberi_sebelumnya=-1,
        status_ptkp="TK/0",
        tahun_pajak=2024,
    )
    assert not hasil["berhasil"]


@pytest.mark.parametrize(
    "tool,sebulan,total",
    [
        (
            "calculate_pph21_permanent_annual",
            {"gaji_pokok": 15_000_000, "iuran_jht_dibayar_pegawai": 300_000, "status_ptkp": "TK/0"},
            {"gaji_pokok": 90_000_000, "iuran_jht_dibayar_pegawai": 1_800_000, "status_ptkp": "TK/0"},
        ),
        (
            "calculate_pph21_permanent_last_period",
            {"gaji_pokok": 20_000_000, "status_ptkp": "TK/1", "pph_sudah_dipotong": 4_000_000},
            {"gaji_pokok": 120_000_000, "status_ptkp": "TK/1", "pph_sudah_dipotong": 4_000_000},
        ),
        (
            "calculate_pph21_pensioner_last_period",
            {"uang_pensiun": 6_300_000, "zakat_via_pembayar_pensiun": 100_000, "status_ptkp": "K/2", "pph_sudah_dipotong": 50_000},
            {"uang_pensiun": 37_800_000, "zakat_via_pembayar_pensiun": 600_000, "status_ptkp": "K/2", "pph_sudah_dipotong": 50_000},
        ),
    ],
)
def test_per_month_values_equal_total(tool, sebulan, total):
    umum = {"tahun_pajak": 2025, "bulan_masa_perolehan": 6}
    a = call_tool(tool, nilai_per_bulan=True, **umum, **sebulan)
    b = call_tool(tool, **umum, **total)
    assert a["berhasil"] and b["berhasil"]
    assert a["pph_terutang"] == b["pph_terutang"]
    assert a["penghasilan_bruto"] == b["penghasilan_bruto"]
    assert "sebulan" in a["asumsi"][0] and "6 bulan" in a["asumsi"][0]


@pytest.mark.parametrize("status", list(PTKPStatus))
@pytest.mark.parametrize("gaji_sebulan", [3_000_000, 12_000_000, 20_000_000, 60_000_000, 400_000_000])
def test_gross_up_last_period_total_allowance_equals_annual_pph(status, gaji_sebulan):
    from taxagent.taxes.pph21.calc import calc_final_period_gross_up

    sudah = sum(
        calc_monthly_ter_gross_up(IncomeComponents(gaji_pokok=gaji_sebulan), status, 2025, m).pph_terutang
        for m in range(1, 12)
    )
    h = calc_final_period_gross_up(
        IncomeComponents(gaji_pokok=gaji_sebulan * 12), status, 2025, sudah
    )
    tunjangan_setahun = h.langkah[0].nilai
    assert tunjangan_setahun == sudah + h.pph_terutang
    assert tunjangan_setahun == h.pph_sebelum_penalti
    assert h.penghasilan_bruto == Decimal(gaji_sebulan * 12) + tunjangan_setahun


@pytest.mark.parametrize("status", list(PTKPStatus))
@pytest.mark.parametrize(
    "gaji",
    [0, 4_000_000, 5_400_000, 5_400_001, 10_000_000, 51_827_997, 68_600_000, 150_000_000, 2_000_000_000],
)
@pytest.mark.parametrize("punya_npwp", [True, False])
def test_gross_up_consistent(status, gaji, punya_npwp):
    h = calc_monthly_ter_gross_up(
        IncomeComponents(gaji_pokok=gaji), status, 2024, 1, punya_npwp=punya_npwp
    )
    tunjangan = h.langkah[0].nilai
    assert h.pph_terutang == tunjangan
    assert h.penghasilan_bruto == Decimal(gaji) + tunjangan


def test_mixed_natura_and_vehicle_condition():
    dasar = {
        "tahun_pajak": 2025,
        "makanan_di_tempat_kerja": 1_000_000,
        "peralatan_kerja": 15_000_000,
        "tempat_tinggal_individual": 3_500_000,
        "fasilitas_olahraga": 1_000_000,
        "olahraga_sebelumnya_tahun_ini": 1_000_000,
        "kendaraan": 4_000_000,
        "rata_rata_bruto_12_bulan": 80_000_000,
    }
    h = call_tool("calculate_taxable_natura", **dasar)
    assert h["natura_kena_pajak"] == "2000000"
    h = call_tool("calculate_taxable_natura", **dict(dasar, pegawai_punya_penyertaan_modal=True))
    assert h["natura_kena_pajak"] == "6000000"
    h = call_tool("calculate_taxable_natura", **dict(dasar, rata_rata_bruto_12_bulan=150_000_000))
    assert h["natura_kena_pajak"] == "6000000"
