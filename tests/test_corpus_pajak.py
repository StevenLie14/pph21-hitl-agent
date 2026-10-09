from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("bs4")
pytest.importorskip("pymupdf")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

import corpus_pajak  # noqa: E402

BARIS_DAFTAR = """
<div class="peraturan-content views-row row-1">
 <div class="views-field views-field-field-nomor-dokumen"><h3 class="field-content">
  <a href="/index.php/id/peraturan/kebijakan-bencana-ntt" hreflang="id">KEP-185/PJ/2026</a></h3></div>
 <div class="views-field views-field-title"><span class="field-content">KEBIJAKAN   ADMINISTRASI</span></div>
 <span class="views-field views-field-field-jenis-dokumen"><strong class="field-content">Keputusan Dirjen Pajak</strong></span>
 <span class="views-field views-field-field-tanggal-peraturan"><strong class="field-content">
  <time class="datetime" datetime="2026-09-02T12:00:00Z">2026-09-02</time></strong></span>
 <span class="views-field views-field-field-status-peraturan"><strong class="field-content">Aktif</strong></span>
</div>
<ul><li class="pager__item pager__item--last"><a href="?title=&amp;page=1261">Last</a></li></ul>
"""


def test_parse_list_and_last_page():
    [x] = corpus_pajak.parse_listing(BARIS_DAFTAR)
    assert x == {"slug": "kebijakan-bencana-ntt", "url": "https://www.pajak.go.id/id/peraturan/kebijakan-bencana-ntt",
                 "nomor": "KEP-185/PJ/2026", "judul": "KEBIJAKAN ADMINISTRASI", "jenis": "Keputusan Dirjen Pajak",
                 "tanggal": "2026-09-02", "status": "Aktif"}
    assert corpus_pajak.last_page(BARIS_DAFTAR) == 1261


def test_parse_detail_one_line_per_clause_and_attachments():
    html = """<h1>KEBIJAKAN ADMINISTRASI</h1>
    <div class="field--name-field-body-dalam-html"><p>DIREKTUR JENDERAL PAJAK,</p>
     <table><tr>
      <td>Menimbang</td>
      <td>:</td>
      <td>a.</td>
      <td>bahwa untuk memberikan <em>kepastian</em>&nbsp;hukum bagi Wajib Pajak yang terdampak bencana</td>
     </tr></table><!-- komentar Word --></div>
    <div class="field--name-field-lampiran-peraturan"><div class="field__item">
     <a href="https://www.pajak.go.id/sites/default/files/lampiran/KEP185PJ2026.pdf">KEP185PJ2026.pdf</a></div></div>"""
    meta, teks = corpus_pajak.parse_detail(html)
    assert teks.splitlines() == ["DIREKTUR JENDERAL PAJAK,", "",
                                 "Menimbang : a. bahwa untuk memberikan kepastian hukum bagi Wajib Pajak yang terdampak bencana"]
    assert meta["judul"] == "KEBIJAKAN ADMINISTRASI"
    assert meta["lampiran"] == [{"nama": "KEP185PJ2026.pdf",
                                 "url": "https://www.pajak.go.id/sites/default/files/lampiran/KEP185PJ2026.pdf"}]


def test_parse_detail_short_body_falls_to_next_selector():
    html = ('<div class="field--name-field-body-dalam-html">kosong</div>'
            '<div class="node__content"><p>' + "Pasal 1 isi peraturan. " * 10 + "</p></div>")
    _, teks = corpus_pajak.parse_detail(html)
    assert teks.startswith("Pasal 1 isi peraturan.")
