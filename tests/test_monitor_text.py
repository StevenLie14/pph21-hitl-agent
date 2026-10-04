from __future__ import annotations

import json
from pathlib import Path

import pytest

from taxagent.monitor import MonitorState, canon_id, parse_feed
from taxagent.monitor.classify import Watchlist, load_watchlist
from taxagent.monitor.enrichment import choose_text_url, enrich
from taxagent.monitor.jdih import candidate_slugs, parse_page
from taxagent.monitor.run import (
    CODE_FINDINGS,
    MonitorResult,
    bpk_sitemap_ids,
    check_bpk,
    check_watchlist,
    run,
)
from taxagent.monitor.text import extract, parse_date

F = Path(__file__).parent / "fixtures" / "pantau"
TEKS = {
    "pmk-168-tahun-2023": "pmk-168-2023", "pp-58-tahun-2023": "pp-58-2023", "pp-80-tahun-2010": "pp-80-2010",
    "101-pmk-010-2016": "pmk-101-2016", "pmk-10-tahun-2025": "pmk-10-2025",
}


def halaman(slug: str) -> str:
    return (F / "halaman" / f"{slug}.html").read_text(encoding="utf-8")


def teks(nama: str) -> str:
    return (F / "teks" / f"{nama}.txt").read_text(encoding="utf-8")


class AmbilPalsu:
    def __init__(self, tambahan: dict[str, tuple[str, str]] | None = None):
        self.tambahan = tambahan or {}
        self.slug_terakhir = None
        self.diminta: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.diminta.append(url)
        if "/dok/" in url:
            slug = url.rsplit("/", 1)[-1]
            self.slug_terakhir = slug
            if slug in self.tambahan:
                return self.tambahan[slug][0].encode()
            p = F / "halaman" / f"{slug}.html"
            if p.exists():
                return p.read_bytes()
            raise OSError(f"404 {url}")
        if "sitemap" in url and "sitemap" in self.tambahan:
            return self.tambahan["sitemap"][0].encode()
        if self.slug_terakhir in self.tambahan:
            return self.tambahan[self.slug_terakhir][1].encode()
        return teks(TEKS[self.slug_terakhir]).encode()


def test_pmk_168_relations_from_json_not_badge():
    h = parse_page(halaman("pmk-168-tahun-2023"))
    assert h.nomor == "PMK 168 TAHUN 2023" and h.judul.startswith("Petunjuk Pelaksanaan Pemotongan")
    assert h.tgl_penetapan == "2023-12-29" and h.tgl_pengundangan == "2023-12-29"
    keluar = {(str(r.identitas), r.jenis_efek) for r in h.relasi if r.arah == "keluar"}
    assert keluar == {
        ("PMK 250 Tahun 2008", "mencabut"),
        ("PMK 252 Tahun 2008", "mencabut"),
        ("PMK 102 Tahun 2016", "mencabut"),
        ("PMK 262 Tahun 2010", "mencabut_sebagian"),
    }


def test_msb_relation_direction_from_name():
    pp58 = parse_page(halaman("pp-58-tahun-2023"))
    pp80 = parse_page(halaman("pp-80-tahun-2010"))
    [r58] = pp58.relasi
    assert (r58.kode, r58.arah, r58.jenis_efek, str(r58.identitas)) == ("MSB", "keluar", "mencabut_sebagian", "PP 80 Tahun 2010")
    masuk = [r for r in pp80.relasi if r.arah == "masuk"]
    assert [(r.kode, r.jenis_efek, str(r.identitas)) for r in masuk] == [("MSB", "mencabut_sebagian", "PP 58 Tahun 2023")]
    pmk10 = parse_page(halaman("pmk-10-tahun-2025"))
    assert [(r.kode, r.arah, r.jenis_efek, str(r.identitas)) for r in pmk10.relasi] == [
        ("U", "masuk", "mengubah", "PMK 72 Tahun 2025")
    ]


def test_download_links_and_text_choice():
    h = parse_page(halaman("101-pmk-010-2016"))
    assert all("/abtrak/" not in u for u in h.url_unduh)
    assert choose_text_url(h).endswith("101~PMK.010~2016Per.pdf")
    assert choose_text_url(parse_page(halaman("pp-80-tahun-2010"))).endswith(".htm")


@pytest.mark.parametrize(
    "ident,slug",
    [("101/PMK.010/2016", "101-pmk-010-2016"), ("PMK 168 Tahun 2023", "pmk-168-tahun-2023"),
     ("PER-11/PJ/2025", "per-11pj2025"), ("PP 80 Tahun 2010", "pp-80-tahun-2010")],
)
def test_slug_candidates(ident, slug):
    assert slug in candidate_slugs(canon_id(ident))


@pytest.mark.parametrize(
    "potongan,iso",
    [("29 Desember 2023", "2023-12-29"), ("I Jamtari2024", "2024-01-01"),
     ("27 Desemfur 2023", "2023-12-27"), ("1 Januari 2011", "2011-01-01")],
)
def test_read_date_tolerates_ocr(potongan, iso):
    assert parse_date(potongan)[0][0] == iso


def test_extract_pmk_168_revocation_list_and_partial():
    e = extract(teks("pmk-168-2023"), canon_id("PMK 168 Tahun 2023"))
    assert (e.in_force_from, e.enacted, e.promulgated, e.retroaktif) == ("2024-01-01", "2023-12-29", "2023-12-29", False)
    assert [(str(p.identitas), p.sebagian) for p in e.revokes] == [
        ("PMK 250 Tahun 2008", False), ("PMK 252 Tahun 2008", False),
        ("PMK 102 Tahun 2016", False), ("PMK 262 Tahun 2010", True),
    ]
    assert e.revokes[-1].bagian == "PASAL 5, PASAL 8, BAGIAN PERTAMA ANGKA I, DAN BAGIAN KEDUA ANGKA I LAMPIRAN"
    assert e.unreadable == []


def test_extract_pp_58_broken_text_layer():
    e = extract(teks("pp-58-2023"), canon_id("PP 58 Tahun 2023"))
    assert e.in_force_from == "2024-01-01"
    assert e.enacted == "2023-12-27"
    [p] = e.revokes
    assert str(p.identitas) == "PP 80 Tahun 2010" and p.sebagian and p.bagian == "PASAL 2 AYAT (3)"


def test_extract_pmk_101_retroactive_and_no_considerans_mismatch():
    e = extract(teks("pmk-101-2016"), canon_id("101/PMK.010/2016"))
    assert e.in_force_from == "diundangkan" and e.promulgated == "2016-06-27" and e.enacted == "2016-06-22"
    assert e.applies_to == ["TAHUN PAJAK 2016"] and e.retroaktif
    assert [str(p.identitas) for p in e.revokes] == ["PMK 122 Tahun 2015"]


def test_extract_pmk_10_2025_empty_promulgation_date_reported():
    e = extract(teks("pmk-10-2025"), canon_id("PMK 10 Tahun 2025"))
    assert e.promulgated is None and "diundangkan" in e.unreadable
    assert e.applies_to == ["MASA PAJAK JANUARI 2025 SAMPAI DENGAN MASA PAJAK DESEMBER 2025"]
    assert e.retroaktif
    assert e.revokes == []


def test_extract_uu_hpp_revocation_does_not_cross_article_title():
    potongan = (
        "Pasal 16 Pada saat Undang-Undang ini mulai berlaku, semua peraturan pelaksanaan dari "
        "Undang-Undang Nomor 7 Tahun 1983 tentang Pajak Penghasilan dan Undang-Undang Nomor 8 Tahun 1983 "
        "tentang Pajak Pertambahan Nilai, dinyatakan masih tetap berlaku sepanjang tidak bertentangan. "
        "Pasal 17 (1) Ketentuan sebagaimana dimaksud dalam Pasal 3 mulai berlaku pada Tahun Pajak 2022. "
        "Pasal 18 Ketentuan Pasal 5 ayat (1) huruf b Peraturan Pemerintah Pengganti Undang-Undang Nomor 1 "
        "Tahun 2020 tentang Kebijakan Keuangan Negara yang telah ditetapkan menjadi Undang-Undang Nomor 2 "
        "Tahun 2020 (Lembaran Negara Republik Indonesia Tahun 2020 Nomor 134), dicabut dan dinyatakan tidak "
        "berlaku. Pasal 19 Undang-Undang ini mulai berlaku pada tanggal diundangkan. Agar setiap orang "
        "mengetahuinya"
    )
    e = extract(potongan, canon_id("UU 7 Tahun 2021"))
    assert [str(p.identitas) for p in e.revokes] == ["PERPPU 1 Tahun 2020", "UU 2 Tahun 2020"]
    assert all(p.sebagian for p in e.revokes)
    assert e.revokes[0].bagian == "KETENTUAN PASAL 5 AYAT (1) HURUF B"
    assert e.in_force_from == "diundangkan"


def test_extract_amendments():
    potongan = (
        "Beberapa ketentuan dalam Peraturan Menteri Keuangan Nomor 10 Tahun 2025 tentang Pajak Penghasilan "
        "Pasal 21 ... diubah sebagai berikut: 1. Ketentuan Pasal 2 diubah. Pasal II Peraturan Menteri ini "
        "mulai berlaku pada tanggal diundangkan. Agar setiap orang mengetahuinya"
    )
    e = extract(potongan, canon_id("PMK 72 Tahun 2025"))
    assert [str(i) for i in e.amends] == ["PMK 10 Tahun 2025"]


def test_decree_without_promulgation_formula_still_read():
    e = extract(teks("kmk-46-ef2-2026"), canon_id("KMK 46/MK/EF.2/2026"))
    assert e.is_decree and e.enacted == "2026-09-29" and e.unreadable == []
    assert e.in_force_from == "2026-09-30"


def test_chained_revocation_marks_intermediate_amendments():
    t = (
        "KETENTUAN PENUTUP Pasal 28 Pada saat Peraturan Menteri ini mulai berlaku, Peraturan Menteri Keuangan Nomor "
        "191/PMK.04/2016 tentang Pembebasan Bea Masuk sebagaimana telah beberapa kali diubah terakhir dengan Peraturan "
        "Menteri Keuangan Nomor 91/PMK.04/2021 tentang Perubahan Kedua, dicabut dan dinyatakan tidak berlaku. Pasal 29 "
        "Peraturan Menteri ini mulai berlaku setelah 60 (enam puluh) hari terhitung sejak tanggal diundangkan. Agar setiap "
        "orang mengetahuinya. Ditetapkan di Jakarta pada tanggal 24 Juni 2026"
    )
    e = extract(t, canon_id("PMK 45 Tahun 2026"))
    assert e.chained_revocation
    assert [str(x.identitas) for x in e.revokes] == ["PMK 191 Tahun 2016", "PMK 91 Tahun 2021"]


def test_electronic_signature_promulgation_date_from_metadata():
    e = extract(teks("pmk-67-2026"), canon_id("PMK 67 Tahun 2026"))
    assert (e.enacted, e.promulgated, e.in_force_from) == ("2026-08-31", None, "diundangkan")
    assert e.unreadable == ["diundangkan"] and not e.is_decree
    assert [str(x.identitas) for x in e.revokes] == ["PMK 44 Tahun 2024"]
    assert e.mulai_berlaku_tanggal is None
    e.promulgated_metadata = "2026-09-08"
    assert e.mulai_berlaku_tanggal == "2026-09-08" and not e.retroaktif


@pytest.mark.parametrize(
    "slug,harus_ada,tidak_boleh",
    [
        ("pmk-168-tahun-2023", [], ["pencabutan", "tanggal", "mulai berlaku"]),
        ("pp-58-tahun-2023", ["mulai berlaku: teks 2024-01-01, metadata relasi JDIH 2023-12-27"], ["pencabutan"]),
        ("pp-80-tahun-2010", ["mulai berlaku: teks 2011-01-01, metadata relasi JDIH 2010-12-20"], ["pencabutan"]),
        ("101-pmk-010-2016", ["tanggal pengundangan: teks 2016-06-27, metadata JDIH 2016-06-22", "berlaku surut"], ["pencabutan"]),
        ("pmk-10-tahun-2025", ["berlaku surut"], []),
    ],
)
def test_text_vs_jdih_metadata_comparison(slug, harus_ada, tidak_boleh):
    p = enrich(slug, AmbilPalsu())
    gabung = " | ".join(p.discrepancies)
    for s in harus_ada:
        assert s in gabung, p.discrepancies
    for s in tidak_boleh:
        assert s not in gabung, p.discrepancies


HALAMAN_SINTETIS = (
    "<title>PMK 90 TAHUN 2027 - Ketentuan Umum Pemotongan | JDIH Kementerian Keuangan</title>\n"
    '\\"TglPenetapan\\":\\"$D2027-06-20T00:00:00.000Z\\" \\"TglPengundangan\\":\\"$D2027-06-21T00:00:00.000Z\\"\n'
    '\\"KodeRelasi\\":\\"C\\",\\"Keterangan\\":null,\\"Jenis\\":\\"Riwayat\\",\\"Nama\\":\\"Mencabut\\",'
    '\\"TglMulaiBerlaku\\":\\"$D2027-01-01T00:00:00.000Z\\",\\"Nomor\\":\\"101/PMK.010/2016\\",'
    '\\"Judul\\":\\"Penyesuaian Besarnya Penghasilan Tidak Kena Pajak\\",\\"Slug\\":\\"101-pmk-010-2016\\"\n'
    '<a href="/api/download/0b5e7a5c-1111-4222-8333-944455556666/2027pmkeuangan90.pdf">'
)
TEKS_SINTETIS = (
    "BAB X KETENTUAN PENUTUP Pasal 7 Pada saat Peraturan Menteri ini mulai berlaku, Peraturan Menteri "
    "Keuangan Nomor 101/PMK.010/2016 tentang Penyesuaian Besarnya Penghasilan Tidak Kena Pajak, dicabut dan "
    "dinyatakan tidak berlaku. Pasal 8 Peraturan Menteri ini mulai berlaku pada tanggal 1 Januari 2027. Agar "
    "setiap orang mengetahuinya, memerintahkan pengundangan Peraturan Menteri ini. Ditetapkan di Jakarta pada "
    "tanggal 20 Juni 2027 MENTERI KEUANGAN Diundangkan di Jakarta pada tanggal 21 Juni 2027"
)
ITEM_SINTETIS = {
    "id": "https://jdih.kemenkeu.go.id/dok/pmk-90-tahun-2027",
    "url": "https://jdih.kemenkeu.go.id/dok/pmk-90-tahun-2027",
    "title": "PMK 90 TAHUN 2027",
    "content_html": "Ketentuan Umum Pemotongan",
    "date_modified": "2027-06-20T12:00:00.000Z",
}


def _feed(*items) -> list:
    data = json.loads((F / "jdih_feed_2026-10-04.json").read_bytes())
    data["items"][:0] = list(items)
    return parse_feed(json.dumps(data))


def test_vague_title_raised_to_basis_because_text_revokes_watchlist():
    status = MonitorState()
    run(_feed(), status, now="2026-10-04T08:00:00")
    ambil = AmbilPalsu({"pmk-90-tahun-2027": (HALAMAN_SINTETIS, TEKS_SINTETIS)})
    h = run(_feed(ITEM_SINTETIS), status, now="2027-06-22T08:00:00", fetch=ambil)
    assert h.exit_code == CODE_FINDINGS
    [c] = h.new_notes
    assert c.kategori == "dasar" and "ptkp" in c.key_terdampak and "PP 58 Tahun 2023" in c.pemicu
    assert any("mencabut PMK 101 Tahun 2016" in a for a in c.alasan)
    assert (c.ditetapkan, c.diundangkan, c.mulai_berlaku_teks, c.retroaktif) == ("2027-06-20", "2027-06-21", "2027-01-01", True)
    assert c.dicabut_teks == [{"identitas": "PMK 101 Tahun 2016", "sebagian": False, "bagian": ""}]
    assert any("berlaku surut" in s for s in c.selisih)


def test_enrichment_failure_becomes_warning_not_failure():
    status = MonitorState()
    run(_feed(), status, now="2026-10-04T08:00:00")

    def ambil_rusak(url):
        raise OSError("timeout")

    item = dict(ITEM_SINTETIS, content_html="Kebijakan Fiskal Umum")
    h = run(_feed(item), status, now="2027-06-22T08:00:00", fetch=ambil_rusak)
    assert h.exit_code == 2 and h.failed_enrichments == 1 and not h.new_notes


def test_watchlist_status_path_finds_new_incoming_relation():
    lengkap = load_watchlist()
    wl = Watchlist(
        tuple(e for e in lengkap.regulations if str(e.identity) in ("PMK 101 Tahun 2016", "PP 80 Tahun 2010")),
        lengkap.keywords, lengkap.keys_from_keywords,
    )
    status = MonitorState()
    h1 = MonitorResult(exit_code=0)
    check_watchlist(status, wl, AmbilPalsu(), "2026-10-04T08:00:00", h1)
    assert not h1.new_notes and set(status.relasi_watchlist) == {"PMK 101 Tahun 2016", "PP 80 Tahun 2010"}

    baru = halaman("101-pmk-010-2016") + (
        '\n\\"KodeRelasi\\":\\"C\\",\\"Keterangan\\":null,\\"Jenis\\":\\"Riwayat\\",\\"Nama\\":\\"Dicabut dengan  \\",'
        '\\"TglMulaiBerlaku\\":\\"$D2027-01-01T00:00:00.000Z\\",\\"Nomor\\":\\"PMK 90 TAHUN 2027\\",'
        '\\"Judul\\":\\"x\\",\\"Slug\\":\\"pmk-90-tahun-2027\\"'
    )
    h2 = MonitorResult(exit_code=0)
    check_watchlist(status, wl, AmbilPalsu({"101-pmk-010-2016": (baru, "")}), "2026-10-11T08:00:00", h2)
    [c] = h2.new_notes
    assert c.identitas == "PMK 90 Tahun 2027" and c.kategori == "dasar" and c.key_terdampak == ["ptkp"]
    assert c.sumber == "jdih_relasi_watchlist"


SITEMAP = (
    '<?xml version="1.0"?><urlset>'
    "<url><loc>https://peraturan.bpk.go.id/Details/342160/pmk-no-1-tahun-2027</loc></url>"
    "<url><loc>https://peraturan.bpk.go.id/Details/340018/pergub-prov-jawa-tengah-no-1-tahun-2027</loc></url>"
    "{tambahan}</urlset>"
)


def test_bpk_sitemap_identity_central_regulations_only():
    daftar = bpk_sitemap_ids(SITEMAP.format(tambahan=""))
    assert [str(i) for i, _ in daftar] == ["PMK 1 Tahun 2027"]


def test_bpk_safety_net_with_seven_day_grace():
    wl = load_watchlist()
    status = MonitorState()
    hasil = MonitorResult(exit_code=0)
    check_bpk(status, wl, AmbilPalsu({"sitemap": (SITEMAP.format(tambahan=""), "")}), "2027-06-01T08:00:00", hasil)
    assert status.bpk_dilihat == {"PMK 1 Tahun 2027": "2027-06-01T08:00:00"} and not status.bpk_tertunda

    loc = "<url><loc>https://peraturan.bpk.go.id/Details/350000/pmk-no-90-tahun-2027</loc></url>"
    halaman_90 = HALAMAN_SINTETIS.replace("Ketentuan Umum Pemotongan", "Penyesuaian Besarnya Penghasilan Tidak Kena Pajak")
    ambil = AmbilPalsu({"sitemap": (SITEMAP.format(tambahan=loc), ""), "pmk-90-tahun-2027": (halaman_90, "")})
    h1 = MonitorResult(exit_code=0)
    check_bpk(status, wl, ambil, "2027-06-03T08:00:00", h1)
    assert "PMK 90 Tahun 2027" in status.bpk_tertunda and not h1.new_notes

    h2 = MonitorResult(exit_code=0)
    check_bpk(status, wl, ambil, "2027-06-11T08:00:00", h2)
    [c] = h2.new_notes
    assert c.sumber == "bpk_sitemap" and c.kategori == "dasar" and "ptkp" in c.key_terdampak
    assert any("tidak muncul di feed JDIH" in a for a in c.alasan)
    assert not status.bpk_tertunda


def test_from_jdih_skips_files_already_in_graph():
    from taxagent.monitor.graph_ingest import ALREADY_PRESENT, from_jdih

    diambil = []

    def ambil(url: str) -> bytes:
        diambil.append(url)
        return halaman("pmk-168-tahun-2023").encode()

    d = from_jdih("pmk-168-tahun-2023", ambil, skip=lambda kunci: kunci == "PMK 168 Tahun 2023")
    assert d.key == "PMK 168 Tahun 2023" and ALREADY_PRESENT in d.notes
    assert len(diambil) == 1


def test_complete_only_text_nodes_not_from_pajak():
    from taxagent.monitor.graph_ingest import is_complete

    class Klien:
        def __init__(self, baris):
            self.baris = baris

        def query(self, cypher, **params):
            return self.baris

    assert is_complete(Klien([{"stub": False, "teks": True, "sumber": "jdih"}]), "x")
    assert not is_complete(Klien([]), "x")
    assert not is_complete(Klien([{"stub": True, "teks": True, "sumber": "jdih"}]), "x")
    assert not is_complete(Klien([{"stub": False, "teks": False, "sumber": "jdih"}]), "x")
    assert not is_complete(Klien([{"stub": False, "teks": True, "sumber": "pajak"}]), "x")


def _pdf(text: str) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    doc.new_page().insert_text((40, 60), text[:80])
    data = doc.tobytes()
    doc.close()
    return data


class _PdfFetch(AmbilPalsu):
    def __call__(self, url: str) -> bytes:
        if "/api/download/" in url:
            return _pdf("PENGHASII.AN TIDAK KENA PAJAK 2o27")
        return super().__call__(url)


def test_scanned_pdf_is_read_from_ocr_text_not_the_text_layer():
    from taxagent.monitor.ocr import OCRResult

    status = MonitorState()
    run(_feed(), status, now="2026-10-04T08:00:00")
    seen: list[bytes] = []

    def ocr(content: bytes) -> OCRResult:
        seen.append(content)
        return OCRResult(TEKS_SINTETIS, "scan", "ocr_cache")

    ambil = _PdfFetch({"pmk-90-tahun-2027": (HALAMAN_SINTETIS, "")})
    h = run(_feed(ITEM_SINTETIS), status, now="2027-06-22T08:00:00", fetch=ambil, ocr=ocr)
    [c] = h.new_notes
    assert seen and seen[0][:5] == b"%PDF-"
    assert c.sumber_teks == "ocr_cache"
    assert c.mulai_berlaku_teks == "2027-01-01" and "ptkp" in c.key_terdampak


def test_scanned_pdf_falls_back_to_text_layer_with_a_note_when_ocr_fails():
    from taxagent.monitor.ocr import OCRResult

    status = MonitorState()
    run(_feed(), status, now="2026-10-04T08:00:00")
    ambil = _PdfFetch({"pmk-90-tahun-2027": (HALAMAN_SINTETIS, "")})
    h = run(_feed(ITEM_SINTETIS), status, now="2027-06-22T08:00:00", fetch=ambil,
            ocr=lambda content: OCRResult(None, "scan", "lapisan_pdf", "exit 1: no GPU"))
    [c] = h.new_notes
    assert c.sumber_teks == "lapisan_pdf"
    assert any("PDF scan tanpa OCR (exit 1: no GPU)" in g for g in c.galat_pengayaan)


def test_keyword_excerpt_reaches_manifest_terms_past_frequent_article_mentions():
    from taxagent.monitor.classify_llm import excerpt, keyword_excerpt

    awal = "Undang-undang tentang harmonisasi peraturan perpajakan. " * 40
    sebutan = " ".join(f"Ketentuan Pasal 21 ayat ({i}) tentang pemotongan oleh pihak lain diubah." + " isi" * 120
                       for i in range(30))
    ptkp = " Penghasilan Tidak Kena Pajak per tahun diberikan paling sedikit sebesar Rp54.000.000,00. "
    teks = awal + sebutan + " lain" * 3000 + ptkp + " penutup" * 500
    assert "Rp54.000.000" not in excerpt(teks)
    k = keyword_excerpt(teks)
    assert "Rp54.000.000" in k and len(k) <= 6000 + 10 * len(" [...] ")
    assert keyword_excerpt("pendek") == "pendek"
    assert keyword_excerpt("x " * 5000, groups=[]) == ("x " * 5000).strip()[:6000]


def test_graph_excerpt_unchanged_by_the_shared_helper():
    from taxagent.monitor.impact import ImpactGraph, graph_excerpt

    g = ImpactGraph({"ptkp": {"istilah": ["ptkp"]}, "bj": {"istilah": ["biaya jabatan"]}}, {}, {}, {}, {})
    teks = "awal " * 400 + " ".join(["PTKP naik"] * 30) + " isi" * 2000 + " biaya jabatan 5%" + " akhir" * 2000
    out = graph_excerpt(teks, g)
    assert out.startswith("awal") and "biaya jabatan 5%" in out and " [...] " in out
