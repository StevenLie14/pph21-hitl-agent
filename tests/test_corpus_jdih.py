from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("pymupdf")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

import corpus_jdih  # noqa: E402


def _halaman(*dokumen: dict) -> str:
    potongan = "".join(f'["$","$L3b",null,{{"data":{json.dumps(d)},"q":""}}]' for d in dokumen)
    return f'<html><script>self.__next_f.push([1,{json.dumps(potongan)}])</script></html>'


DOK = {"produk_hukum_id": "fbd45e3b", "slug": "kmk-185-tahun-2026", "bentuk": "Keputusan Menteri", "no": 185,
       "tahun": 2026, "nomor": "KMK 185 TAHUN 2026", "teu": "Badan Pendidikan dan Pelatihan Keuangan",
       "judul": "Pedoman \"Analisis\" Kebutuhan", "full_text_pdf": "/api/download/123/KMK 185 Tahun 2026.pdf"}


def test_listing_item_reads_documents_from_payload():
    item = corpus_jdih.item_listing(_halaman(DOK, dict(DOK, produk_hukum_id="kedua", slug="pmk-1-tahun-2026")))
    assert [x["slug"] for x in item] == ["kmk-185-tahun-2026", "pmk-1-tahun-2026"]
    assert item[0]["judul"] == 'Pedoman "Analisis" Kebutuhan' and item[0]["full_text_pdf"].endswith(".pdf")


def test_listing_item_duplicate_document_counted_once():
    assert len(corpus_jdih.item_listing(_halaman(DOK, DOK))) == 1


def test_listing_item_empty_page():
    assert corpus_jdih.item_listing("<html>tidak ada hasil</html>") == []


def test_url_with_spaces_quoted():
    assert corpus_jdih._safe_url("https://jdih.kemenkeu.go.id/api/download/1/KMK 185.pdf") == \
        "https://jdih.kemenkeu.go.id/api/download/1/KMK%20185.pdf"


def test_htm_text_windows_1252_and_lines():
    isi = ("<html><head><title>x</title></head><body><p>KEPUTUSAN MENTERI KEUANGAN</p>"
           "<p>Pasal&nbsp;1</p><p>Tarif 15–persen</p></body></html>").encode("cp1252")
    teks = corpus_jdih.htm_text(isi)
    assert teks.splitlines() == ["KEPUTUSAN MENTERI KEUANGAN", "Pasal 1", "Tarif 15–persen"]


def _korpus_satu_dokumen(tmp_path: Path, url_unduh: list[str]) -> None:
    (tmp_path / "daftar").mkdir()
    (tmp_path / "daftar" / "2026.jsonl").write_text(json.dumps(DOK) + "\n", encoding="utf-8")
    (tmp_path / "halaman").mkdir()
    (tmp_path / "halaman" / f"{DOK['produk_hukum_id']}.json").write_text(
        json.dumps({"url": "https://jdih.kemenkeu.go.id/dok/kmk-185-tahun-2026", "url_unduh": url_unduh}),
        encoding="utf-8")


def test_file_url_listing_first_then_page_links(tmp_path):
    _korpus_satu_dokumen(tmp_path, ["https://jdih.kemenkeu.go.id/api/download/FullText/2026/KMK185.htm",
                                    "https://jdih.kemenkeu.go.id/lain.docx",
                                    "https://jdih.kemenkeu.go.id/api/download/FullText/2026/KMK185.pdf"])
    assert corpus_jdih._file_urls(DOK, tmp_path) == [
        "https://jdih.kemenkeu.go.id/api/download/123/KMK 185 Tahun 2026.pdf",
        "https://jdih.kemenkeu.go.id/api/download/FullText/2026/KMK185.pdf",
        "https://jdih.kemenkeu.go.id/api/download/FullText/2026/KMK185.htm",
    ]


def test_download_tries_fallback_link_when_listing_404(tmp_path, monkeypatch):
    cadangan = "https://jdih.kemenkeu.go.id/api/download/FullText/2026/KMK185.htm"
    _korpus_satu_dokumen(tmp_path, [cadangan])
    htm = ("<html><body><p>KEPUTUSAN MENTERI KEUANGAN NOMOR 185 TAHUN 2026</p><p>"
           + "isi keputusan " * 20 + "</p></body></html>").encode()
    dicoba = []

    def palsu(url, timeout=60.0):
        dicoba.append(url)
        if "FullText" not in url:
            raise corpus_jdih.SourceError(f"gagal mengambil {url}: HTTP Error 404: Not Found")
        return htm

    monkeypatch.setattr(corpus_jdih, "fetch", palsu)
    a = corpus_jdih.argparse.Namespace(dir=tmp_path, only=None)
    corpus_jdih.cmd_download(a)
    rek = json.loads((tmp_path / "berkas" / f"{DOK['produk_hukum_id']}.json").read_text(encoding="utf-8"))
    assert len(dicoba) == 2 and rek["url"] == cadangan and rek["jenis"] == "htm"
    assert not (tmp_path / "gagal.jsonl").exists()


def test_download_all_links_failed_recorded_once(tmp_path, monkeypatch):
    _korpus_satu_dokumen(tmp_path, ["https://jdih.kemenkeu.go.id/api/download/FullText/2026/KMK185.htm"])

    def palsu(url, timeout=60.0):
        raise corpus_jdih.SourceError(f"gagal mengambil {url}: HTTP Error 500")

    monkeypatch.setattr(corpus_jdih, "fetch", palsu)
    corpus_jdih.cmd_download(corpus_jdih.argparse.Namespace(dir=tmp_path, only=None))
    baris = (tmp_path / "gagal.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(baris) == 1 and json.loads(baris[0])["galat"].count("HTTP Error 500") == 2
    assert not (tmp_path / "berkas" / f"{DOK['produk_hukum_id']}.json").exists()


def test_page_reads_validity_and_latest_history():
    from taxagent.monitor.jdih import parse_page

    isi = ('<title>252/PMK.03/2008 - Petunjuk | JDIH</title>{\\"TglPenetapan\\":\\"$D2008-12-31T00:00:00.000Z\\",'
           '\\"TglPengundangan\\":\\"$D2008-12-31T00:00:00.000Z\\",\\"TglMulaiBerlaku\\":\\"$D2008-12-31T00:00:00.000Z\\",'
           '\\"TglSelesaiBerlaku\\":\\"$D2023-12-29T00:00:00.000Z\\"} [\\"$\\",\\"span\\",null,{\\"className\\":'
           '\\"riwayat-badge riwayat-badge--danger\\",\\"children\\":\\"Dicabut\\"}],[\\"$\\",\\"span\\",null,'
           '{\\"className\\":\\"riwayat-latest\\"')
    h = parse_page(isi, "https://jdih.kemenkeu.go.id/dok/252-pmk-03-2008")
    assert (h.tgl_mulai_berlaku, h.tgl_selesai_berlaku, h.riwayat_terakhir) == ("2008-12-31", "2023-12-29", "Dicabut")


def test_refresh_only_pages_without_validity(tmp_path):
    lama, baru = tmp_path / "a.json", tmp_path / "b.json"
    lama.write_text(json.dumps({"nomor": "x"}), encoding="utf-8")
    baru.write_text(json.dumps({"nomor": "y", "tgl_mulai_berlaku": None}), encoding="utf-8")
    assert corpus_jdih._already_fetched(lama, False) and not corpus_jdih._already_fetched(lama, True)
    assert corpus_jdih._already_fetched(baru, True) and not corpus_jdih._already_fetched(tmp_path / "c.json", True)
