from __future__ import annotations

import pytest

from taxagent.taxes.pph21.calc import FinalIncomeType, PPh21Result, apply_ikn_facility, calc_lump_sum_third_year
from taxagent.taxes.pph21.calc.object_codes import load_object_codes
from taxagent.tools import call_tool


def _kode(h: dict) -> str | None:
    assert h["berhasil"], h
    return h["objek_pajak"]["kode"] if h["objek_pajak"] else None


def test_ikn_last_period_example_case_11_per_11_2025():
    h = call_tool("calculate_pph21_permanent_last_period", gaji_pokok=100_000_000, status_ptkp="TK/0", tahun_pajak=2025,
                  pph_sudah_dipotong=2_000_000, fasilitas_ikn=True)
    assert h["pph_terutang"] == "50000"
    assert h["pph_ditanggung_pemerintah"] == "50000"
    assert _kode(h) == "21-100-32" and h["objek_pajak"]["formulir"] == "BPA1"
    assert "PMK No. 28 Tahun 2024 Pasal 138" in h["dasar_hukum"]
    assert any(l["label"] == "PPh 21 yang dipotong dari penghasilan pegawai" and l["nilai"] == "0"
               for l in h["langkah"])
    assert "fasilitas PPh 21 ditanggung pemerintah IKN" in h["ringkasan_masukan"]


def test_ikn_monthly_ter_example_case_11():
    h = call_tool("calculate_pph21_permanent_monthly", gaji_pokok=10_000_000, status_ptkp="TK/0", tahun_pajak=2025,
                  masa_pajak=3, fasilitas_ikn=True)
    assert h["pph_terutang"] == "200000" and h["pph_ditanggung_pemerintah"] == "200000"
    assert h["jenis_perhitungan"].endswith("_ikn")


def test_without_ikn_no_dtp_and_permanent_employee_code():
    h = call_tool("calculate_pph21_permanent_monthly", gaji_pokok=10_000_000, status_ptkp="TK/0", tahun_pajak=2025,
                  masa_pajak=3)
    assert "pph_ditanggung_pemerintah" not in h and _kode(h) == "21-100-01"


@pytest.mark.parametrize("arg, pesan", [({"punya_npwp": False}, "NPWP"), ({"gross_up": True}, "gross_up")])
def test_ikn_rejected(arg, pesan):
    h = call_tool("calculate_pph21_permanent_monthly", gaji_pokok=10_000_000, status_ptkp="TK/0", tahun_pajak=2025,
                  masa_pajak=3, fasilitas_ikn=True, **arg)
    assert not h["berhasil"] and pesan in h["galat"]


def test_ikn_ends_december_2035():
    with pytest.raises(ValueError, match="2035"):
        apply_ikn_facility(PPh21Result(jenis_perhitungan="pegawai_tetap_bulanan_ter", tahun_pajak=2036), True)


@pytest.mark.parametrize("arg, kode", [
    ({"upah_per_periode": 300_000, "skema": "harian"}, "21-100-29"),
    ({"upah_per_periode": 3_000_000, "skema": "harian"}, "21-100-31"),
    ({"upah_per_periode": 5_000_000, "skema": "bulanan", "status_ptkp": "TK/0"}, "21-100-27"),
])
def test_ikn_non_permanent_employee(arg, kode):
    h = call_tool("calculate_pph21_non_permanent", tahun_pajak=2025, fasilitas_ikn=True, **arg)
    assert _kode(h) == kode and h["objek_pajak"]["final"] is True
    assert h.get("pph_ditanggung_pemerintah", "0") == h["pph_terutang"] or h["pph_terutang"] == "0"


def test_severance_third_year_pasal_17_rate():
    h = call_tool("calculate_pph21_final", jenis="pesangon", jumlah_bruto=100_000_000, tahun_pajak=2025,
                  tahun_pembayaran_ke=3)
    assert h["pph_terutang"] == "9000000"
    assert _kode(h) == "21-100-25" and h["objek_pajak"]["final"] is False
    assert "PP No. 68 Tahun 2009 Pasal 6" in h["dasar_hukum"]
    assert "tahun kalender ke-3" in h["ringkasan_masukan"]


def test_severance_second_year_stays_final():
    h = call_tool("calculate_pph21_final", jenis="pesangon", jumlah_bruto=100_000_000, tahun_pajak=2025,
                  tahun_pembayaran_ke=2)
    assert h["pph_terutang"] == "2500000" and _kode(h) == "21-401-01"


def test_third_year_without_npwp_20_percent_higher():
    h = call_tool("calculate_pph21_final", jenis="manfaat_pensiun", jumlah_bruto=100_000_000, tahun_pajak=2025,
                  tahun_pembayaran_ke=4, punya_npwp=False)
    assert h["pph_terutang"] == "10800000" and h["penalti_non_npwp"] == "1800000"


def test_third_year_cumulative_within_calendar_year():
    h = calc_lump_sum_third_year(FinalIncomeType.PESANGON, 50_000_000, 2025, dibayar_sebelumnya_tahun_ini=50_000_000)
    assert h.pph_terutang == 6_500_000


def test_honorarium_third_year_rejected():
    h = call_tool("calculate_pph21_final", jenis="honorarium_pns", golongan="III", jumlah_bruto=1_000_000,
                  tahun_pajak=2025, tahun_pembayaran_ke=3)
    assert not h["berhasil"] and "pesangon" in h["galat"]


@pytest.mark.parametrize("nama, arg, kode", [
    ("calculate_pph21_permanent_annual", {"gaji_pokok": 120_000_000, "status_ptkp": "K/1"}, "21-100-01"),
    ("calculate_pph21_pensioner_monthly", {"uang_pensiun": 5_000_000, "status_ptkp": "K/0", "masa_pajak": 1},
     "21-100-02"),
    ("calculate_pph21_non_permanent", {"upah_per_periode": 300_000, "skema": "harian"}, "21-100-24"),
    ("calculate_pph21_non_permanent", {"upah_per_periode": 3_000_000, "skema": "harian"}, "21-100-30"),
    ("calculate_pph21_non_permanent", {"upah_per_periode": 5_000_000, "skema": "bulanan", "status_ptkp": "TK/0"},
     "21-100-35"),
    ("calculate_pph21_non_employee", {"penghasilan_bruto": 10_000_000, "jenis_jasa": "tenaga_ahli"}, "21-100-07"),
    ("calculate_pph21_non_employee", {"penghasilan_bruto": 10_000_000, "jenis_jasa": "Seniman_Influencer"},
     "21-100-33"),
    ("calculate_pph21_commissioner", {"penghasilan_bruto": 10_000_000, "status_ptkp": "TK/0"}, "21-100-10"),
    ("calculate_pph21_direct_pasal_17", {"jenis": "mantan_pegawai", "penghasilan_bruto": 10_000_000}, "21-100-11"),
    ("calculate_pph21_direct_pasal_17", {"jenis": "peserta_pensiun_pegawai", "penghasilan_bruto": 10_000_000},
     "21-100-12"),
    ("calculate_pph21_direct_pasal_17", {"jenis": "peserta_kegiatan", "jenis_kegiatan": "perlombaan",
                                       "penghasilan_bruto": 10_000_000}, "21-100-36"),
    ("calculate_pph21_final", {"jenis": "manfaat_pensiun", "jumlah_bruto": 60_000_000}, "21-401-02"),
    ("calculate_pph21_final", {"jenis": "honorarium_pns", "golongan": "III", "jumlah_bruto": 1_000_000}, "21-402-02"),
    ("calculate_pph21_final", {"jenis": "honorarium_pns", "golongan": "IV", "jumlah_bruto": 1_000_000}, "21-402-03"),
    ("calculate_pph21_final", {"jenis": "honorarium_pns", "golongan": "I", "jumlah_bruto": 1_000_000}, "21-402-04"),
    ("calculate_pph_pasal_26", {"penghasilan_bruto": 10_000_000}, "27-100-99"),
])
def test_tax_object_code(nama, arg, kode):
    assert _kode(call_tool(nama, tahun_pajak=2025, **arg)) == kode


def test_empty_service_kind_does_not_guess_code():
    h = call_tool("calculate_pph21_non_employee", penghasilan_bruto=10_000_000, tahun_pajak=2025)
    assert h["objek_pajak"] is None
    assert any("jenis penerima" in a for a in h["asumsi"])


def test_unknown_service_kind_error():
    h = call_tool("calculate_pph21_non_employee", penghasilan_bruto=10_000_000, tahun_pajak=2025, jenis_jasa="dukun")
    assert not h["berhasil"] and "tenaga_ahli" in h["galat"]


def test_code_list_complete_and_consistent():
    data = load_object_codes()
    kode = data["kode"]
    tidak_final_bp21 = [k for k, v in kode.items() if v["formulir"] == "BP21" and not v["final"]]
    assert len(tidak_final_bp21) == 24
    final_bp21 = [k for k, v in kode.items() if v["formulir"] == "BP21" and v["final"]]
    assert len(final_bp21) == 10
    for peta in ("jenis_jasa", "jenis_kegiatan", "honorarium_golongan"):
        assert set(data[peta].values()) <= set(kode)


def test_legal_basis_topic_enum_from_regulation_map():
    from taxagent.taxes.pph21.calc.rates import load_regulations
    from taxagent.taxes.pph21.tool_schemas import DasarHukumArgs

    sk = DasarHukumArgs.model_json_schema()["properties"]["topic"]
    assert sk["type"] == "string" and set(sk["enum"]) == set(load_regulations())
    assert "premi_pemberi_kerja" in sk["description"] and "search_faq" in sk["description"]


def test_faq_link_points_to_pdf_page_or_question_sentence():
    from taxagent.tools.regulation_graph import faq_location, faq_number

    assert faq_number("faq-dtp#28") == 28 and faq_number("faq-x#") is None
    pdf = faq_location({"url": "https://pajak.go.id/faq-dtp", "pertanyaan": "Apakah DTP dibayar tunai?",
                        "pdf_url": "https://pajak.go.id/f.pdf", "pdf_halaman": 17})
    assert pdf["tautan"] == "https://pajak.go.id/f.pdf#page=17" and pdf["lampiran_pdf_halaman"] == 17
    web = faq_location({"url": "https://pajak.go.id/faq-npwp", "pertanyaan": "Bagaimana cara memadankan NIK, NPWP?",
                        "pdf_url": "", "pdf_halaman": 0})
    assert web["tautan"] == "https://pajak.go.id/faq-npwp#:~:text=Bagaimana%20cara%20memadankan%20NIK%2C%20NPWP%3F"


def test_pdf_location_from_page_text(tmp_path):
    from taxagent.corpus.faq import pdf_location

    it = {"bagian": [{"jenis": "html", "teks": "x"},
                     {"jenis": "pdf", "berkas": "a.pdf", "halaman": 1, "url": "u.pdf", "teks": "1. Apa itu PTKP?"},
                     {"jenis": "pdf", "berkas": "a.pdf", "halaman": 2, "url": "u.pdf",
                      "teks": "28.\nJika\nPPh\n21 biasanya ditanggung perusahaan (gross\nup), apakah PPh 21 DTP"}]}
    assert pdf_location(tmp_path, it, "Jika PPh 21 biasanya ditanggung perusahaan (gross up), apakah PPh 21 DTP "
                                    "tersebut harus dibayarkan ke karyawan?") == ("u.pdf", 2)
    assert pdf_location(tmp_path, it, "Pertanyaan yang tidak ada di lampiran mana pun") is None
