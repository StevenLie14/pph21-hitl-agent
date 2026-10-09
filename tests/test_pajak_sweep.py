import json

import pytest
from test_graph_ingest import TEKS, Klien

from taxagent.cli import monitor as cli_pantau
from taxagent.corpus.ingest import Document
from taxagent.corpus.pajak_go_id import LISTING_URL, parse_listing
from taxagent.monitor import graph_ingest as M
from taxagent.monitor.jdih import search_url
from taxagent.monitor.ocr import OCRResult
from taxagent.monitor.pajak_sweep import became_inactive, compare, reason, sweep
from taxagent.monitor.sources import SourceError

pymupdf = pytest.importorskip("pymupdf")

BADAN = "Pasal 1 Ketentuan pemotongan pajak penghasilan diatur sebagai berikut. " * 4


def _baris(slug, nomor, status="Aktif", jenis="Peraturan Dirjen Pajak"):
    return (f'<div class="peraturan-content"><div class="views-field views-field-field-nomor-dokumen">'
            f'<h3><a href="/id/peraturan/{slug}">{nomor}</a></h3></div>'
            f'<div class="views-field views-field-title"><span>Judul {nomor}</span></div>'
            f'<span class="views-field views-field-field-jenis-dokumen"><strong>{jenis}</strong></span>'
            '<span class="views-field views-field-field-tanggal-peraturan"><strong>'
            '<time datetime="2027-01-05T12:00:00Z">x</time></strong></span>'
            f'<span class="views-field views-field-field-status-peraturan"><strong>{status}</strong></span></div>')


def _pager(akhir):
    return f'<ul><li class="pager__item pager__item--last"><a href="?page={akhir}">Last</a></li></ul>'


def _flight(*dok):
    potongan = "".join(f'["$","$L3b",null,{{"data":{json.dumps(d)},"q":""}}]' for d in dok)
    return f"<script>self.__next_f.push([1,{json.dumps(potongan)}])</script>"


def _detail(badan=BADAN, lampiran=""):
    html = f'<h1>JUDUL</h1><div class="field--name-field-body-dalam-html"><p>{badan}</p></div>'
    if lampiran:
        html += (f'<div class="field--name-field-lampiran-peraturan"><div class="field__item">'
                 f'<a href="{lampiran}">lampiran.pdf</a></div></div>')
    return html


def _pdf(teks):
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), teks)
    return doc.tobytes()


def _ambil(peta):
    def ambil(url):
        if url not in peta:
            raise SourceError(f"tidak ada: {url}")
        v = peta[url]
        return v if isinstance(v, bytes) else v.encode("utf-8")
    return ambil


JDIH_PER9 = {"produk_hukum_id": "u9", "slug": "per-9pj2027", "bentuk": "Peraturan Unit Eselon I",
             "nomor": "PER-9/PJ/2027"}
JDIH_LAIN = {"produk_hukum_id": "u1", "slug": "pmk-9-tahun-2027", "bentuk": "Peraturan Menteri",
             "nomor": "PMK 9 TAHUN 2027"}


def test_compare_new_slug_and_changed_label():
    potret = {"a": {"nomor": "PER-1/PJ/2020", "judul": "Judul PER-1/PJ/2020", "jenis": "Peraturan Dirjen Pajak",
                    "tanggal": "2027-01-05", "status": "Aktif"}}
    item = parse_listing(_baris("a", "PER-1/PJ/2020", "Tidak Berlaku") + _baris("c", "PER-2/PJ/2027"))
    baru, berubah = compare(potret, item)
    assert [x["slug"] for x in baru] == ["c"]
    [(x, beda)] = berubah
    assert x["slug"] == "a" and beda == {"status": ("Aktif", "Tidak Berlaku")}
    assert became_inactive(beda) and not became_inactive({"status": ("Tidak Berlaku", "Aktif")})
    assert reason(beda) == "status pajak.go.id: Aktif -> Tidak Berlaku"


def test_crawl_all_pages_and_failed_pages_recorded():
    ambil = _ambil({LISTING_URL.format(0): _baris("a", "PER-1/PJ/2020") + _pager(2),
                    LISTING_URL.format(2): _baris("b", "PER-2/PJ/2020") + _baris("a", "PER-1/PJ/2020")})
    item, gagal = sweep(ambil)
    assert [(x["slug"], x["halaman_listing"]) for x in item] == [("a", 0), ("b", 2)] and gagal == [1]


def test_search_jdih_local_corpus_then_site_with_exact_key():
    def tanpa_jaringan(url):
        raise AssertionError("tidak boleh ke jaringan")
    assert M.find_in_jdih("PER-9/PJ/2027", "PER-9/PJ/2027", tanpa_jaringan, {"PER-9/PJ/2027": "per-9pj2027"}) \
        == "per-9pj2027"
    ambil = _ambil({search_url({"q": "PER-9/PJ/2027"}): _flight(JDIH_LAIN, JDIH_PER9)})
    assert M.find_in_jdih("PER-9/PJ/2027", "PER-9/PJ/2027", ambil, {}) == "per-9pj2027"
    ambil = _ambil({search_url({"q": "PER-9/PJ/2027"}): _flight(JDIH_LAIN)})
    assert M.find_in_jdih("PER-9/PJ/2027", "PER-9/PJ/2027", ambil, {}) is None


def test_local_jdih_index_from_listing(tmp_path):
    (tmp_path / "daftar").mkdir()
    (tmp_path / "daftar" / "2027.jsonl").write_text(json.dumps(JDIH_PER9) + "\n", encoding="utf-8")
    assert M.local_jdih_index(tmp_path) == {"PER-9/PJ/2027": "per-9pj2027"}


def test_pajak_document_taken_from_jdih_when_jdih_has_it(monkeypatch):
    [item] = parse_listing(_baris("per-9-pj-2027", "PER-9/PJ/2027"))
    monkeypatch.setattr(M, "from_jdih", lambda slug, ambil, ocr=None: Document(
        key="PER-9/PJ/2027", source="jdih", id=slug, text=TEKS))
    ambil = _ambil({search_url({"q": "PER-9/PJ/2027"}): _flight(JDIH_PER9)})
    d = M.pajak_document(item, ambil, {})
    assert d.source == "jdih" and d.id == "per-9pj2027" and "per-9-pj-2027" in d.notes[-1]


def test_pajak_document_missing_in_jdih_or_search_failed():
    [item] = parse_listing(_baris("per-9-pj-2027", "PER-9/PJ/2027"))
    detail = {item["url"]: _detail()}
    d = M.pajak_document(item, _ambil({**detail, search_url({"q": "PER-9/PJ/2027"}): _flight(JDIH_LAIN)}), {})
    assert d.source == "pajak" and d.text and "tidak ada di JDIH" in d.notes[-1]
    d = M.pajak_document(item, _ambil(detail), {})
    assert d.source == "pajak" and d.notes[-1].startswith("pencarian JDIH gagal")


def test_empty_body_text_from_pdf_attachment():
    [item] = parse_listing(_baris("se-1", "PER-9/PJ/2027"))
    url_pdf = "https://www.pajak.go.id/sites/default/files/lampiran/PER9.pdf"
    ambil = _ambil({item["url"]: _detail(badan="", lampiran=url_pdf), url_pdf: _pdf("Pasal 1 isi lampiran")})
    d = M.from_pajak(item, ambil, ocr=lambda isi: OCRResult(None, "digital", "lapisan_pdf"))
    assert "Pasal 1 isi lampiran" in d.text and d.text_source == "lampiran_pdf"
    d = M.from_pajak(item, ambil, ocr=lambda isi: OCRResult("Pasal 1 hasil OCR", "scan", "ocr"))
    assert d.text == "Pasal 1 hasil OCR" and d.text_source == "lampiran_ocr"
    d = M.from_pajak(item, ambil, ocr=lambda isi: OCRResult(None, "scan", "lapisan_pdf", "OCR tidak tersedia"))
    assert d.text is None and "lampiran tidak memberi teks" in d.notes[-1]


class KlienSumber(Klien):
    def query(self, cypher, **p):
        if "RETURN p.stub AS stub, p.has_text AS teks, p.doc_source AS sumber" in cypher:
            n = self.node.get(p["k"])
            return [{"stub": n["stub"], "teks": n["punya_teks"], "sumber": n["sumber"]}] if n else []
        if "count(e) AS pencabut" in cypher:
            n = self.node.get(p["k"])
            return [{"sumber": n["sumber"], "teks": n["punya_teks"], "pencabut": 0}] if n else []
        return super().query(cypher, **p)


def test_jdih_replaces_pajak_node_but_not_vice_versa():
    d = Document(key="PER 9 Tahun 2027", source="jdih", id="per-9pj2027", text=TEKS, text_source="lapisan_pdf")
    k = KlienSumber(node={"PER 9 Tahun 2027": {"stub": False, "sumber": "pajak", "punya_teks": True}})
    [h] = M.ingest([d], k, dry_run=True)
    assert "dilewati" not in h
    k = KlienSumber(node={"PER 9 Tahun 2027": {"stub": False, "sumber": "jdih", "punya_teks": True}})
    assert M.ingest([d], k, dry_run=True) == [{"kunci": "PER 9 Tahun 2027", "dilewati": "sudah ada di graf"}]


def test_pajak_sweep_inserts_new_and_changed_then_saves_snapshot(tmp_path, monkeypatch):
    dir_pajak, dir_jdih = tmp_path / "pajak", tmp_path / "jdih"
    dir_pajak.mkdir()
    dir_jdih.mkdir()
    lama = parse_listing(_baris("per-1", "PER-1/PJ/2020"))[0]
    (dir_pajak / "daftar.jsonl").write_text(json.dumps(lama) + "\n", encoding="utf-8")
    monkeypatch.setattr(cli_pantau, "PAJAK_DIR", dir_pajak)
    monkeypatch.setattr(cli_pantau, "JDIH_DIR", dir_jdih)
    listing = _baris("per-1", "PER-1/PJ/2020", "Tidak Berlaku") + _baris("per-2", "PER-2/PJ/2027")
    item = {x["slug"]: x for x in parse_listing(listing)}
    ambil = _ambil({LISTING_URL.format(0): listing, item["per-1"]["url"]: _detail(), item["per-2"]["url"]: _detail(),
                    search_url({"q": "PER-1/PJ/2020"}): _flight(), search_url({"q": "PER-2/PJ/2027"}): _flight()})
    k = KlienSumber(node={"PER-1/PJ/2020": {"stub": False, "sumber": "pajak", "punya_teks": True}})
    lap = cli_pantau.pajak_sweep(dry_run=False, max_pages=None, max_ingest=10, ocr=False, log="",
                                 output_dir=str(tmp_path / "lap"), fetch=ambil, client=k, echo=lambda s: None)
    assert (lap["baru"], lap["berubah"], lap["diproses"]) == (1, 1, 2)
    assert [x["slug"] for x in lap["slug_baru"]] == ["per-2"] and lap["slug_hilang"] == []
    alasan_ = {d["slug"]: d["alasan"] for d in lap["dokumen"]}
    assert alasan_ == {"per-2": "sapu: slug baru di halaman listing 0",
                       "per-1": "sapu: status pajak.go.id: Aktif -> Tidak Berlaku"}
    assert [t["slug"] for t in lap["temuan"]] == ["per-1"]
    assert any("CREATE (m:Ingest)" in c and p["m"].get("reason") for c, p in k.tulis)
    potret = json.loads((dir_pajak / "sapu_potret.json").read_text(encoding="utf-8"))
    assert potret["per-1"]["status"] == "Tidak Berlaku" and "per-2" in potret
    assert "per-2" in (dir_pajak / "daftar.jsonl").read_text(encoding="utf-8")
    assert (dir_pajak / "detail" / "per-1.json").exists() and (tmp_path / "lap").exists()
    lap = cli_pantau.pajak_sweep(dry_run=True, max_pages=None, max_ingest=10, ocr=False, log="",
                                 output_dir=str(tmp_path / "lap"), fetch=ambil, client=k, echo=lambda s: None)
    assert (lap["baru"], lap["berubah"]) == (0, 0)


def test_partially_revoked_label_not_out_of_force():
    sebagian, penuh = "Diubah/Disempurnakan/Dicabut sebagian", "Diubah/Disempurnakan dan Sudah dicabut"
    assert not became_inactive({"status": ("Aktif", sebagian)})
    assert became_inactive({"status": ("Aktif", penuh)}) and became_inactive({"status": ("Aktif", "Dicabut")})
    assert became_inactive({"status": (sebagian, "Dicabut")})
    assert not became_inactive({"status": ("Dicabut", penuh)})


def test_one_failed_attachment_does_not_fail_document():
    [item] = parse_listing(_baris("se-1", "PER-9/PJ/2027"))
    rusak, baik = "https://www.pajak.go.id/a.pdf", "https://www.pajak.go.id/b.pdf"
    html = _detail(badan="").replace("</div>", "</div>" + "".join(
        f'<div class="field--name-field-lampiran-peraturan"><div class="field__item"><a href="{u}">x.pdf</a></div></div>'
        for u in (rusak, baik)), 1)
    d = M.from_pajak(item, _ambil({item["url"]: html, baik: _pdf("Pasal 1 isi")}),
                     ocr=lambda isi: OCRResult(None, "digital", "lapisan_pdf"))
    assert "Pasal 1 isi" in d.text and any("gagal diunduh" in c for c in d.notes)


def test_sweep_new_slug_cut_by_limit_still_new_next_week(tmp_path, monkeypatch):
    dir_pajak = tmp_path / "pajak"
    dir_pajak.mkdir()
    (tmp_path / "jdih").mkdir()
    monkeypatch.setattr(cli_pantau, "PAJAK_DIR", dir_pajak)
    monkeypatch.setattr(cli_pantau, "JDIH_DIR", tmp_path / "jdih")
    listing = _baris("per-2", "PER-2/PJ/2027") + _baris("per-3", "PER-3/PJ/2027")
    item = {x["slug"]: x for x in parse_listing(listing)}
    ambil = _ambil({LISTING_URL.format(0): listing, item["per-2"]["url"]: _detail(), item["per-3"]["url"]: _detail(),
                    search_url({"q": "PER-2/PJ/2027"}): _flight(), search_url({"q": "PER-3/PJ/2027"}): _flight()})
    jalan = {"max_pages": None, "ocr": False, "log": "", "output_dir": str(tmp_path / "lap"), "fetch": ambil,
             "client": KlienSumber(), "echo": lambda s: None}
    lap = cli_pantau.pajak_sweep(dry_run=False, max_ingest=1, **jalan)
    assert lap["diproses"] == 1 and any("max-ingest" in g for g in lap["galat"])
    assert cli_pantau.pajak_sweep(dry_run=True, max_ingest=10, **jalan)["baru"] == 1
