from __future__ import annotations

from taxagent.taxes.pph21.prompt import SYSTEM_PROMPT
from taxagent.tools import call_tool


def test_monthly_pension_sent_as_annual_asks_confirmation():
    h = call_tool("calculate_pph21_pensioner_last_period", uang_pensiun=6300000, status_ptkp="K/2",
                  tahun_pajak=2024, pph_sudah_dipotong=173250)
    assert h["berhasil"] and len(h["perlu_konfirmasi"]) == 1
    assert "nilai_per_bulan=true" in h["perlu_konfirmasi"][0]
    assert "Rp6.300.000" in h["ringkasan_masukan"] and "per bulan" not in h["ringkasan_masukan"]


def test_pension_with_monthly_values_asks_no_confirmation():
    h = call_tool("calculate_pph21_pensioner_last_period", uang_pensiun=6300000, nilai_per_bulan=True,
                  bulan_masa_perolehan=12, status_ptkp="K/2", tahun_pajak=2024, pph_sudah_dipotong=173250)
    assert h["perlu_konfirmasi"] == []
    r = h["ringkasan_masukan"]
    assert "uang pensiun Rp6.300.000 per bulan x 12 bulan" in r
    assert "pph sudah dipotong Rp173.250" in r and "Rp173.250 per bulan" not in r
    assert "penghasilan bruto yang dihitung Rp75.600.000" in r


def test_short_earning_period_without_annualising_asks_confirmation():
    arg = {"gaji_pokok": 62000000, "zakat_via_pemberi_kerja": 3100000, "status_ptkp": "TK/0", "tahun_pajak": 2024,
               "bulan_masa_perolehan": 4, "pph_sudah_dipotong": 3255000}
    h = call_tool("calculate_pph21_permanent_last_period", **arg)
    assert len(h["perlu_konfirmasi"]) == 1 and "disetahunkan=true" in h["perlu_konfirmasi"][0]
    h2 = call_tool("calculate_pph21_permanent_last_period", disetahunkan=True, **arg)
    assert h2["perlu_konfirmasi"] == [] and "disetahunkan" in h2["ringkasan_masukan"]


def test_normal_year_without_confirmation():
    h = call_tool("calculate_pph21_permanent_annual", gaji_pokok=120000000, status_ptkp="TK/0", tahun_pajak=2024)
    assert h["perlu_konfirmasi"] == []
    assert h["ringkasan_masukan"].startswith("PPh 21 pegawai tetap, setahun (Pasal 17); tahun pajak 2024, 12 bulan")


def test_monthly_summary_and_no_confirmation():
    h = call_tool("calculate_pph21_permanent_monthly", gaji_pokok=10000000, status_ptkp="TK/0", tahun_pajak=2024,
                  masa_pajak=3, punya_npwp=False)
    assert h["perlu_konfirmasi"] == []
    r = h["ringkasan_masukan"]
    assert "masa pajak Maret 2024" in r and "status TK/0" in r and "tanpa NPWP" in r and "gaji pokok Rp10.000.000" in r


def test_other_tools_and_errors():
    h = call_tool("calculate_pph21_non_employee", penghasilan_bruto=7000000, tahun_pajak=2024)
    assert h["ringkasan_masukan"].startswith("PPh 21 bukan pegawai") and h["perlu_konfirmasi"] == []
    g = call_tool("calculate_pph21_permanent_annual", status_ptkp="TK/0", tahun_pajak=2024)
    assert g["berhasil"] is False and "ringkasan_masukan" not in g
    assert "ringkasan_masukan" not in call_tool("lookup_ptkp", kawin=True, jumlah_tanggungan=1)


def test_prompt_requires_summary_and_explains_confirmation():
    assert "Data yang dihitung" in SYSTEM_PROMPT and "ringkasan_masukan" in SYSTEM_PROMPT
    assert "perlu_konfirmasi" in SYSTEM_PROMPT and '"Mohon\n  periksa"' in SYSTEM_PROMPT
    assert "Jangan memanggil ulang tool atau mengubah argumen karena `perlu_konfirmasi`" in SYSTEM_PROMPT


def test_confirmation_and_summary_before_result():
    h = call_tool("calculate_pph21_permanent_annual", gaji_pokok=120000000, status_ptkp="TK/0", tahun_pajak=2024)
    assert list(h)[:3] == ["berhasil", "perlu_konfirmasi", "ringkasan_masukan"]


def test_december_with_zero_withholding_asks_confirmation():
    arg = {"gaji_pokok": 15000000, "nilai_per_bulan": True, "status_ptkp": "K/2", "tahun_pajak": 2025}
    h = call_tool("calculate_pph21_permanent_last_period", pph_sudah_dipotong=0, **arg)
    assert h["pph_terutang"] == "9975000" and len(h["perlu_konfirmasi"]) == 1
    assert "PPh setahun penuh" in h["perlu_konfirmasi"][0] and "TER bulanan" in h["perlu_konfirmasi"][0]
    assert call_tool("calculate_pph21_permanent_last_period", pph_sudah_dipotong=9900000, **arg)["perlu_konfirmasi"] == []


def test_december_withholding_estimated_from_ter():
    arg = {"gaji_pokok": 15000000, "nilai_per_bulan": True, "status_ptkp": "K/2", "tahun_pajak": 2025}
    h = call_tool("calculate_pph21_permanent_last_period", pph_sudah_dipotong=0, pph_sudah_dipotong_ter_sama=True, **arg)
    assert h["berhasil"] and h["pph_terutang"] == "75000" and h["perlu_konfirmasi"] == []
    assert any("Rp900.000 x 11 masa = Rp9.900.000" in a for a in h["asumsi"])
    g = call_tool("calculate_pph21_permanent_last_period", gaji_pokok=180000000, status_ptkp="K/2", tahun_pajak=2025,
                  pph_sudah_dipotong=0, pph_sudah_dipotong_ter_sama=True)
    assert g["berhasil"] is False and "nilai_per_bulan=true" in g["galat"]


def test_prompt_requires_asking_december_withholding():
    assert "pph_sudah_dipotong_ter_sama=true" in SYSTEM_PROMPT
