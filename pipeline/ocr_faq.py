from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pymupdf
from paddle_common import make_ocr, ocr_page

FAQ_DIR = Path(os.environ.get("PPH21_DATA") or "data") / "faq"


def output_path(b: dict) -> Path:
    name = Path(b["berkas"]).stem
    return FAQ_DIR / "ocr" / name / (f"{b['halaman']:04d}.txt" if b["jenis"] == "pdf" else "gambar.txt")


def main() -> None:
    ap = argparse.ArgumentParser(description='OCR the DJP FAQ parts marked ``perlu_ocr`` by ``pipeline/faq.py collect``: scanned PDF pages and images in the')
    ap.add_argument("--device", default="gpu")
    a = ap.parse_args()
    jobs = [b for f in sorted((FAQ_DIR / "item").glob("*.json"))
            for b in json.loads(f.read_text(encoding="utf-8"))["bagian"]
            if b["perlu_ocr"] and not output_path(b).exists()]
    print(f"{len(jobs)} bagian perlu OCR", flush=True)
    if not jobs:
        return
    ocr = make_ocr(a.device)
    for b in jobs:
        f = output_path(b)
        f.parent.mkdir(parents=True, exist_ok=True)
        if b["jenis"] == "pdf":
            with pymupdf.open(FAQ_DIR / "lampiran" / b["berkas"]) as d:
                text = ocr_page(ocr, d[b["halaman"] - 1], f.parent / "_hal.png")
        else:
            png = f.parent / "_gambar.png"
            pymupdf.Pixmap(str(FAQ_DIR / "gambar" / b["berkas"])).save(png)
            try:
                text = "\n".join(t for r in ocr.predict(str(png)) for t in r["rec_texts"])
            finally:
                png.unlink(missing_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(f)
        print(f"{b['berkas']} {b.get('halaman', '')}: {len(text)} karakter", flush=True)


if __name__ == "__main__":
    main()
