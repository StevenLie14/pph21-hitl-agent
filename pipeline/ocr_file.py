from __future__ import annotations

import argparse
import tempfile
import time
from pathlib import Path

import pymupdf
from paddle_common import make_ocr, ocr_page


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("output")
    ap.add_argument("--device", default="gpu", help="gpu | cpu (~2 detik/halaman di RTX 4050 vs 1-3 menit di CPU)")
    ap.add_argument("--threads", dest="threads", type=int, default=5)
    a = ap.parse_args()

    ocr = make_ocr(a.device, a.threads)
    pages = []
    with tempfile.TemporaryDirectory() as tmp, pymupdf.open(a.pdf) as doc:
        for p, page in enumerate(doc, 1):
            t0 = time.time()
            pages.append(ocr_page(ocr, page, Path(tmp) / f"{p:04d}.png"))
            print(f"hal {p}/{doc.page_count} {time.time() - t0:.1f}s", flush=True)
    Path(a.output).write_text("\n".join(pages), encoding="utf-8")


if __name__ == "__main__":
    main()
