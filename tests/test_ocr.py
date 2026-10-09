import subprocess
from pathlib import Path

import pytest

pymupdf = pytest.importorskip("pymupdf")

from taxagent.monitor.ocr import ocr_if_scanned  # noqa: E402


def _pdf(scan: bool) -> bytes:
    doc = pymupdf.open()
    hal = doc.new_page()
    if scan:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 80), 0)
        pix.clear_with(255)
        hal.insert_image(hal.rect, pixmap=pix)
    else:
        hal.insert_text((72, 72), "Penghasilan Tidak Kena Pajak Rp54.000.000,00")
    return doc.tobytes()


def _ocr_palsu(teks="Rp54.000.000,00 (lima puluh empat juta rupiah)", kode=0):
    panggilan = []

    def jalankan(cmd, **kw):
        panggilan.append(cmd)
        if kode == 0:
            Path(cmd[cmd.index("--device") - 1]).write_text(teks, encoding="utf-8")
        return subprocess.CompletedProcess(cmd, kode, "", "galat paddle")

    return jalankan, panggilan


def test_digital_pdf_not_ocred(tmp_path):
    jalankan, panggilan = _ocr_palsu()
    h = ocr_if_scanned(_pdf(scan=False), tmp_path, jalankan)
    assert h.text is None and h.pdf_kind == "digital" and not panggilan


def test_scanned_pdf_ocred_then_from_cache(tmp_path):
    jalankan, panggilan = _ocr_palsu()
    isi = _pdf(scan=True)
    h = ocr_if_scanned(isi, tmp_path, jalankan)
    assert h.pdf_kind == "scan" and h.source == "ocr" and "lima puluh empat juta" in h.text
    h2 = ocr_if_scanned(isi, tmp_path, jalankan)
    assert h2.source == "ocr_cache" and h2.text == h.text and len(panggilan) == 1


def test_ocr_failure_falls_back_to_pdf_layer(tmp_path):
    jalankan, _ = _ocr_palsu(kode=1)
    h = ocr_if_scanned(_pdf(scan=True), tmp_path, jalankan)
    assert h.text is None and h.source == "lapisan_pdf" and "galat paddle" in h.error
    assert not list(tmp_path.glob("*.txt"))
