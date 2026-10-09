from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paddle_common import DPI, ENGINE, make_ocr  # noqa: E402


def page_range(spec: str | None, n: int) -> list[int]:
    if not spec:
        return list(range(1, n + 1))
    result: list[int] = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        result += list(range(int(a), int(b or a) + 1))
    return [p for p in result if 1 <= p <= n]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("output")
    ap.add_argument("--pages", dest="pages", help="mis. 11-25 atau 3,5-7 (default semua)")
    ap.add_argument("--device", default="gpu")
    ap.add_argument("--threads", dest="threads", type=int, default=5)
    a = ap.parse_args()

    ocr = make_ocr(a.device, a.threads)
    out = {"mesin": ENGINE, "dpi": DPI, "halaman": []}
    with tempfile.TemporaryDirectory() as tmp, pymupdf.open(a.pdf) as doc:
        for p in page_range(a.pages, doc.page_count):
            t0 = time.time()
            png = Path(tmp) / f"{p:04d}.png"
            pix = doc[p - 1].get_pixmap(dpi=DPI)
            pix.save(png)
            boxes = []
            for r in ocr.predict(str(png)):
                for text, score, (x0, y0, x1, y1) in zip(r["rec_texts"], r["rec_scores"], r["rec_boxes"].tolist()):
                    boxes.append({"teks": text, "skor": round(float(score), 4),
                                  "x0": int(x0), "y0": int(y0), "x1": int(x1), "y1": int(y1)})
            out["halaman"].append({"nomor": p, "lebar": pix.width, "tinggi": pix.height, "kotak": boxes})
            print(f"hal {p}/{doc.page_count} {time.time() - t0:.1f}s", flush=True)
    Path(a.output).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
