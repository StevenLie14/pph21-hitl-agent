import json

import pymupdf

from taxagent.corpus import faq

HTML = """<html><body>
<div class="field field--name-body field__item"><a href="/id">ID</a> | <a href="/en">EN</a></div>
<article class="node node--type-faq"><h1>FAQ Contoh</h1><div class="node__content">
<p>1. Apakah PMK 168 Tahun 2023 berlaku untuk pegawai tetap?</p><p>Ya, sejak 1 Januari 2024.</p>
<p>2. Bagaimana tarif efektif dihitung?</p><p>Lihat PP 58 Tahun 2023.</p>
<img src="/sites/default/files/gambar.png">
<div class="field field--name-field-berkas"><a href="/system/files/2025-11/FAQ%20Contoh.pdf">FAQ Contoh.pdf</a></div>
</div></article></body></html>"""


def test_parse_detail_body_node_not_header():
    d = faq.parse_detail(HTML, "https://www.pajak.go.id/id/faq-contoh")
    assert d["judul"] == "FAQ Contoh"
    assert "EN" not in d["teks"] and "Apakah PMK 168" in d["teks"]
    assert "FAQ Contoh.pdf" not in d["teks"]
    assert d["pdf"] == ["https://www.pajak.go.id/system/files/2025-11/FAQ%20Contoh.pdf"]
    assert d["gambar"] == ["https://www.pajak.go.id/sites/default/files/gambar.png"]


def test_numbered_pairs_and_fallback():
    teks = faq.parse_detail(HTML, "https://x/y")["teks"]
    ps = faq.qa_pairs("FAQ Contoh", teks)
    assert [p["nomor"] for p in ps] == [1, 2]
    assert ps[0]["jawaban"].startswith("Ya, sejak")
    satu = faq.qa_pairs("Batasan File Upload SPT", "Ukuran berkas paling besar 2 MB.")
    assert satu == [{"nomor": 0, "pertanyaan": "Batasan File Upload SPT", "jawaban": "Ukuran berkas paling besar 2 MB."}]


def _pdf_tabel(f, baris):
    d = pymupdf.open()
    h = d.new_page()
    h.insert_text((40, 80), "No")
    h.insert_text((120, 80), "Pertanyaan")
    h.insert_text((380, 80), "Jawaban")
    y = 110
    for n, q, a in baris:
        h.insert_text((40, y + 1), f"{n}.")
        h.insert_text((76, y), q)
        h.insert_text((260, y + 1), a)
        y += 40
    d.save(f)


def test_table_pairs_per_column(tmp_path):
    f = tmp_path / "t.pdf"
    _pdf_tabel(f, [(1, "Apakah THR dihitung?", "Tidak, hanya gaji tetap."),
                   (2, "Kapan diuji?", "Masa Januari 2025.")])
    ps = faq.table_qa_pairs(f)
    assert ps == [{"nomor": 1, "pertanyaan": "Apakah THR dihitung?", "jawaban": "Tidak, hanya gaji tetap."},
                  {"nomor": 2, "pertanyaan": "Kapan diuji?", "jawaban": "Masa Januari 2025."}]


def test_table_pairs_empty_without_header(tmp_path):
    f = tmp_path / "b.pdf"
    d = pymupdf.open()
    d.new_page().insert_text((40, 80), "Bukan tabel FAQ")
    d.save(f)
    assert faq.table_qa_pairs(f) == []


def test_item_text_uses_ocr_when_present(tmp_path):
    b = {"jenis": "pdf", "berkas": "x__1.pdf", "halaman": 2, "teks": "", "perlu_ocr": True}
    it = {"bagian": [{"jenis": "html", "teks": "badan", "perlu_ocr": False}, b]}
    assert faq.item_text(tmp_path, it) == ("badan", 1)
    o = faq.ocr_file(tmp_path, b)
    o.parent.mkdir(parents=True)
    o.write_text("hasil ocr", encoding="utf-8")
    assert faq.item_text(tmp_path, it) == ("badan\nhasil ocr", 0)


class _Klien:
    def __init__(self, ada):
        self.ada, self.jalan = ada, []

    def run(self, c, **p):
        self.jalan.append((c, p))

    def query(self, c, **p):
        return [{"k": k} for k in p["ks"] if k in self.ada]


def test_plan_and_write_refer_only_to_graph_regulations(tmp_path):
    (tmp_path / "item").mkdir()
    (tmp_path / "item" / "faq-contoh.json").write_text(json.dumps({
        "slug": "faq-contoh", "judul": "FAQ Contoh", "url": "https://x", "tanggal": None, "diambil": "2026-10-13",
        "bagian": [{"jenis": "html", "perlu_ocr": False, "teks": faq.parse_detail(HTML, "https://x")["teks"]}]}),
        encoding="utf-8")
    node, rujuk, ring = faq.graph_plan(tmp_path)
    assert ring == {"halaman": 1, "tanya_jawab": 2, "belum_ocr": 0, "dipecah": 1, "jawaban_dipotong": 0, "node": 2}
    assert {r["kunci"] for r in rujuk} == {"PMK 168 Tahun 2023", "PP 58 Tahun 2023"}
    k = _Klien({"PMK 168 Tahun 2023"})
    hasil = faq.write_graph(k, node, rujuk)
    assert hasil["merujuk"] == 1 and hasil["kunci_tidak_di_graf"] == ["PP 58 Tahun 2023"]
    assert not any("MERGE (p:Regulation" in c for c, _ in k.jalan)


def test_long_answers_split_into_parts_with_header(tmp_path):
    paragraf = [f"Paragraf {i}. " + "Natura berupa fasilitas kantor dikecualikan dari objek. " * 8 for i in range(12)]
    teks = "\n\n".join(paragraf)
    bagian = faq.split_answer(teks)
    assert len(bagian) > 1 and all(len(b) <= faq.PART_TARGET + 600 for b in bagian)
    assert " ".join(bagian).split() == teks.split()
    assert faq.split_answer("pendek") == ["pendek"]
    assert all(len(b) <= faq.PART_TARGET for b in faq.split_answer("kata " * 2000))

    (tmp_path / "item").mkdir()
    (tmp_path / "item" / "faq-natura.json").write_text(json.dumps({
        "slug": "faq-natura", "judul": "FAQ Terkait PMK-66 Tahun 2023", "url": "https://x", "tanggal": None,
        "diambil": "2026-10-13", "bagian": [{"jenis": "html", "perlu_ocr": False, "teks": teks}]}), encoding="utf-8")
    node, _, ring = faq.graph_plan(tmp_path)
    assert ring["tanya_jawab"] == 1 and ring["jawaban_dipotong"] == 1 and ring["node"] == len(bagian)
    assert [n["id"] for n in node][:2] == ["faq-natura#0-1", "faq-natura#0-2"]
    assert all(n["jawaban"].startswith("FAQ: FAQ Terkait PMK-66 Tahun 2023\n") for n in node)
    assert node[0]["jumlah_bagian_jawaban"] == len(bagian)
    from taxagent.tools.regulation_graph import faq_number
    assert faq_number("faq-natura#0-2") == 0 and faq_number("faq-x#28") == 28
