from __future__ import annotations

import pytest

from taxagent.corpus.merge import (
    IndexEntry,
    SourceDoc,
    check_doubtful,
    listing_id,
    merge_sources,
    similarity,
    title_from_text,
)


@pytest.mark.parametrize("jenis, nomor, harap", [
    ("Peraturan Menteri Keuangan", "55 TAHUN 2026", "PMK 55 Tahun 2026"),
    ("Peraturan Menteri Keuangan", "PMK 43 TAHUN 2026", "PMK 43 Tahun 2026"),
    ("Peraturan Menteri Keuangan", "101/PMK.010/2016", "PMK 101 Tahun 2016"),
    ("Peraturan Menteri", "PMK 168 TAHUN 2023", "PMK 168 Tahun 2023"),
    ("Keputusan Dirjen Pajak", "251/PJ/2025", "KEP-251/PJ/2025"),
    ("Keputusan Dirjen Pajak", "KEP-185/PJ/2026", "KEP-185/PJ/2026"),
    ("Peraturan Dirjen Pajak", "4 TAHUN 2024", "PER-4/PJ/2024"),
    ("Peraturan Unit Eselon I", "PerDJP 17/PJ/2008", "PER-17/PJ/2008"),
    ("Keputusan Menteri Keuangan", "41/MK/EF.2/2026", "KMK 41/EF2/2026"),
    ("Keputusan Menteri", "KMK Nomor 14/MK/EF.2/2026", "KMK 14/EF2/2026"),
    ("Keputusan Menteri Keuangan", "25/MK.10/2020", "KMK 25/MK10/2020"),
    ("Peraturan Pemerintah", "NOMOR 73 TAHUN 2016", "PP 73 Tahun 2016"),
    ("Perpu", "1 TAHUN 2020", "PERPPU 1 Tahun 2020"),
    ("Peraturan Pemerintah", "PP 61TAHUN2003", "PP 61 Tahun 2003"),
    ("Undang-Undang", "UU 10TAHUN2004", "UU 10 Tahun 2004"),
    ("Peraturan Dirjen Pajak", "PER-67/PJ./2009", "PER-67/PJ/2009"),
    ("Keputusan Dirjen Pajak", "KEP - 12/PJ.BT5/1989", "KEP-12/PJBT5/1989"),
    ("Peraturan Pemerintah", "147 TAHUN 2000", "PP 147 Tahun 2000"),
    ("Keputusan Presiden", "42 TAHUN 1989", "KEPPRES 42 Tahun 1989"),
    ("Keputusan Menteri", "Kpres 81 TAHUN 2003", "KEPPRES 81 Tahun 2003"),
    ("Peraturan Menteri Keuangan", "39.1/PMK.011/2008", "PMK 39.1 Tahun 2008"),
    ("Peraturan Menteri", "206.2/PMK.01/2014", "PMK 206.2 Tahun 2014"),
    ("Keputusan Unit Eselon I", "KEP-007.1/PP/2011", "KEP-7.1/PP/2011"),
])
def test_key_from_various_formats(jenis, nomor, harap):
    assert str(listing_id(jenis, nomor)) == harap


@pytest.mark.parametrize("jenis, nomor", [
    ("Peraturan Menteri Perdagangan", "02/M-DAG/PER/1/2010"),
    ("Pengumuman", "PENG-14/PJ.09/2020"),
    ("Monografi Hukum", ""),
])
def test_without_key(jenis, nomor):
    assert listing_id(jenis, nomor) is None


def _m(sumber, id_, jenis, nomor, judul="Judul", ada_teks=True, mutu=None):
    return SourceDoc(sumber, id_, jenis, nomor, judul, None, ada_teks, mutu)


def test_jdih_primary_pajak_only_supplement():
    jdih = [_m("jdih", "j1", "Peraturan Menteri", "PMK 168 TAHUN 2023", "Petunjuk Pelaksanaan Pemotongan Pajak")]
    pajak = [
        _m("pajak", "p1", "Peraturan Menteri Keuangan", "168 TAHUN 2023", "PETUNJUK PELAKSANAAN PEMOTONGAN PAJAK"),
        _m("pajak", "p2", "Peraturan Dirjen Pajak", "PER-16/PJ/2016"),
        _m("pajak", "p3", "Peraturan Dirjen Pajak", "PER-16/PJ/2016"),
        _m("pajak", "p4", "Pengumuman", "PENG-1/PJ/2020"),
    ]
    indeks, hit = merge_sources(jdih, pajak)
    assert [(e.sumber, e.id) for e in indeks] == [("jdih", "j1"), ("pajak", "p2"), ("pajak", "p4")]
    assert indeks[0].pasangan == "p1" and indeks[0].kemiripan_judul == 1.0
    assert hit["cocok"] == 1 and hit["hanya_pajak"] == 2 and hit["pajak_duplikat"] == 1 and hit["pajak_tanpa_kunci"] == 1


def test_pajak_replaces_textless_jdih_or_unused():
    jdih = [_m("jdih", "j1", "Peraturan Menteri", "PMK 1 TAHUN 2020", ada_teks=False),
            _m("jdih", "j2", "Peraturan Menteri", "PMK 2 TAHUN 2020", mutu="tidak_terpakai"),
            _m("jdih", "j3", "Peraturan Menteri", "PMK 3 TAHUN 2020", mutu="perlu_dicek")]
    pajak = [_m("pajak", f"p{i}", "Peraturan Menteri Keuangan", f"{i} TAHUN 2020") for i in (1, 2, 3)]
    indeks, hit = merge_sources(jdih, pajak)
    assert {e.id for e in indeks if e.sumber == "pajak"} == {"p1", "p2"}
    assert hit["pajak_mengganti_jdih"] == 2


def test_title_similarity_tolerates_writing_style():
    assert similarity("Cipta Kerja", "CIPTA KERJA (KLASTER KEMUDAHAN BERUSAHA BIDANG PERPAJAKAN)") == 1.0
    assert similarity("Pencabutan Peraturan Menteri Keuangan", "PENCABUTANPERATURANMENTERIKEUANGAN") > 0.9
    assert similarity("Penetapan Tarif Bea Masuk atas Impor Kacang Kedelai",
                      "PENGENAAN BEA MASUK ANTI DUMPING TERHADAP IMPOR HOT ROLLED COIL") < 0.5
    assert similarity("", "apa saja") is None


def test_subnumbered_paired_and_not_colliding_with_base_number():
    jdih = [_m("jdih", "j1", "Peraturan Menteri", "131.1/PMK.07/2007", "Alokasi Definitif Dana Bagi Hasil"),
            _m("jdih", "j2", "Peraturan Menteri", "PMK 1 TAHUN 2007", "Hal Lain")]
    pajak = [_m("pajak", "p1", "Peraturan Menteri Keuangan", "131.1/PMK.07/2007", "ALOKASI DEFINITIF DANA BAGI HASIL")]
    indeks, hit = merge_sources(jdih, pajak)
    assert [e.kunci for e in indeks] == ["PMK 131.1 Tahun 2007", "PMK 1 Tahun 2007"]
    assert indeks[0].pasangan == "p1" and hit["cocok"] == 1 and hit["hanya_pajak"] == 0


def test_empty_pajak_text_not_counted_as_text():
    jdih = [_m("jdih", "j1", "Peraturan Menteri", "PMK 1 TAHUN 2020", ada_teks=False)]
    pajak = [_m("pajak", "p1", "Peraturan Menteri Keuangan", "1 TAHUN 2020", mutu="tidak_terpakai"),
             _m("pajak", "p2", "Peraturan Dirjen Pajak", "PER-3/PJ/2020", mutu="tidak_terpakai")]
    indeks, hit = merge_sources(jdih, pajak)
    assert [(e.sumber, e.id, e.catatan) for e in indeks] == [("jdih", "j1", ["tanpa teks"]),
                                                             ("pajak", "p2", ["tanpa teks"])]
    assert hit["pajak_teks_kosong"] == 2 and hit["pajak_mengganti_jdih"] == 0


def _e(sumber, id_, judul, pasangan):
    return IndexEntry(sumber, id_, "PP 30 Tahun 2005", "Peraturan Pemerintah", "30 TAHUN 2005", judul, 2005, None,
                      pasangan=pasangan, kemiripan_judul=0.0)


_TEKS_PP30 = ("PERATURAN PEMERINTAH REPUBLIK INDONESIA NOMOR 30 TAHUN 2005 TENTANG PERUBAHAN ATAS PERATURAN "
              "PEMERINTAH NOMOR 63 TAHUN 2003 TENTANG PERLAKUAN PAJAK PERTAMBAHAN NILAI DENGAN RAHMAT TUHAN YANG "
              "MAHA ESA PRESIDEN REPUBLIK INDONESIA, Menimbang: bahwa dalam rangka ...")


def test_doubt_check_same_text_wrong_jdih_listing_title():
    j, p = _e("jdih", "j", "Perusahaan Umum Kehutanan Negara (Perum Perhutani)", "p"), \
        _e("pajak", "p", "PERUBAHAN ATAS PERATURAN PEMERINTAH NOMOR 63 TAHUN 2003", "j")
    assert check_doubtful(j, p, _TEKS_PP30, _TEKS_PP30 + " sedikit beda") == "sama"
    assert j.judul_teks.startswith("PERUBAHAN ATAS PERATURAN PEMERINTAH NOMOR 63 TAHUN 2003")
    assert j.pasangan == "p"


def test_doubt_check_releases_when_pajak_textless_and_title_differs():
    teks = ("PERATURAN MENTERI KEUANGAN NOMOR 140/PMK.01/2006 TENTANG PEDOMAN PELAKSANAAN ANALISIS BEBAN KERJA "
            "DI LINGKUNGAN DEPARTEMEN KEUANGAN MENTERI KEUANGAN, Menimbang ...")
    j, p = _e("jdih", "j", "Pedoman Pelaksanaan Analisis Beban Kerja di Lingkungan Departemen Keuangan", "p"), \
        _e("pajak", "p", "PENETAPAN ALOKASI SEMENTARA DANA BAGI HASIL PAJAK PENGHASILAN", "j")
    assert check_doubtful(j, p, teks, None) == "lepas"
    assert j.pasangan is None and p.pasangan is None and j.judul_teks is None


def test_title_from_text():
    assert title_from_text(_TEKS_PP30).endswith("PERLAKUAN PAJAK PERTAMBAHAN NILAI")
    assert title_from_text("tanpa judul") is None
