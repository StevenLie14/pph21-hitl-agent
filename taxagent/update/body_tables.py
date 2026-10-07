from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from ..corpus.text_source import JDIH_PDFS, SourceText

OCR_DIR = JDIH_PDFS.parent / "ocr"
NL = chr(10)

_RE_RATE = re.compile(r"^\s*\d+(?:[.,]\d+)?\s*%\s*$")
_RE_TER = re.compile(r"TARIF\s+EFEKTIF\s+(?:BULANAN|HARIAN)", re.I)


@dataclass
class Reflow:
    text: str
    pages: list[int] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)


def has_bracket_table(page_text: str) -> bool:
    return (len(re.findall(r"di\s*atas", page_text, re.I)) >= 2 and "Rp" in page_text and "%" in page_text
            and not _RE_TER.search(page_text))


def candidate_pages(content: bytes, page_texts: list[str] | None = None) -> list[int]:
    import pymupdf

    from .ter_table import has_ter_table, table_pages

    if page_texts is None:
        with pymupdf.open(stream=content, filetype="pdf") as doc:
            page_texts = [p.get_text() for p in doc]
    if sum(len(t.strip()) for t in page_texts) < 50 * max(1, len(page_texts)):
        selected = list(range(1, len(page_texts) + 1))
    else:
        selected = [i for i, t in enumerate(page_texts, 1) if has_bracket_table(t)]
    if selected and has_ter_table(" ".join(page_texts)):
        ter = set(table_pages(content))
        selected = [i for i in selected if i not in ter]
    return selected


def corpus_pages(source: SourceText, ocr_dir: Path = OCR_DIR) -> list[str] | None:
    if not source.jdih_id:
        return None
    folder = Path(ocr_dir) / source.jdih_id
    if not folder.is_dir():
        return None
    return [f.read_text(encoding="utf-8") for f in sorted(folder.glob("[0-9]*.txt"))] or None


def _gap(boxes: list[dict], width: float) -> float | None:
    rates = [k for k in boxes if _RE_RATE.match(k["teks"])]
    if len(rates) < 2:
        return None
    y0, y1 = min(k["y0"] for k in rates), max(k["y1"] for k in rates)
    spans = sorted((k["x0"], k["x1"]) for k in boxes
                   if k["y1"] >= y0 and k["y0"] <= y1 and (k["x1"] - k["x0"]) < 0.6 * width)
    gaps, edge = [], None
    for a, b in spans:
        if edge is not None and a > edge:
            gaps.append((edge, a))
        edge = b if edge is None else max(edge, b)
    gaps = [(a, b) for a, b in gaps if 0.35 * width <= (a + b) / 2 <= 0.9 * width]
    if not gaps:
        return None
    a, b = max(gaps, key=lambda g: g[1] - g[0])
    return (a + b) / 2


def _lines(boxes: list[dict]) -> list[str]:
    if not boxes:
        return []
    height = statistics.median(k["y1"] - k["y0"] for k in boxes)
    out, group, anchor = [], [], None
    for k in sorted(boxes, key=lambda k: (k["y0"] + k["y1"]) / 2):
        yc = (k["y0"] + k["y1"]) / 2
        if anchor is not None and yc - anchor > 0.5 * height:
            out.append(" ".join(x["teks"].strip() for x in sorted(group, key=lambda x: x["x0"])))
            group, anchor = [], None
        if anchor is None:
            anchor = yc
        group.append(k)
    out.append(" ".join(x["teks"].strip() for x in sorted(group, key=lambda x: x["x0"])))
    return out


def _join(boxes: list[dict]) -> str:
    return " ".join(_lines(boxes))


def rebuild_page(page: dict) -> tuple[str | None, str]:
    boxes = [k for k in page["kotak"] if k["teks"].strip()]
    if not boxes:
        return None, "halaman kosong"
    width = page["lebar"]
    gap = _gap(boxes, width)
    if gap is None:
        return None, "celah kolom tidak terlihat"
    h = statistics.median(k["y1"] - k["y0"] for k in boxes)
    spans = [k for k in boxes if k["x0"] < gap < k["x1"]]
    rates = sorted((k for k in boxes if _RE_RATE.match(k["teks"]) and k["x0"] >= gap), key=lambda k: k["y0"])
    if len(rates) < 2:
        return None, "kurang dari dua sel tarif"
    first, last = rates[0]["y0"] - 0.5 * h, rates[-1]["y0"]
    in_rows = [k for k in boxes if k not in spans and first <= k["y0"] <= rates[-1]["y1"]]
    left_x = min((k["x0"] for k in in_rows if k["x1"] <= gap), default=None)
    if left_x is None:
        return None, "kolom kiri kosong"
    header_right = [k for k in boxes if k not in spans and k["x0"] >= gap and first - 4 * h <= k["y0"] < first]
    top = min((k["y0"] for k in header_right), default=first) - 0.5 * h
    below = sorted((k for k in boxes if k["y0"] > last), key=lambda k: k["y0"])
    end = next((k["y0"] for k in below if k in spans or k["x0"] < left_x - 2 * h), None)
    if end is None:
        return None, "akhir tabel tidak terlihat"
    table = [k for k in boxes if k not in spans and top <= k["y0"] < end and k["x0"] >= left_x - 2 * h]
    if any(k in spans for k in boxes if top <= k["y0"] < end):
        return None, "baris selebar halaman di dalam tabel"
    starts = [r["y0"] - 0.5 * h for r in rates]
    header = [k for k in table if k["y0"] < starts[0]]
    rows: list[list[dict]] = [[] for _ in rates]
    for k in table:
        if k["y0"] >= starts[0]:
            rows[max(i for i, s in enumerate(starts) if s <= k["y0"])].append(k)
    written = []
    if header:
        written.append(" ".join(x for x in (_join([k for k in header if k["x1"] <= gap]),
                                            _join([k for k in header if k["x0"] >= gap])) if x))
    for row in rows:
        left, right = _join([k for k in row if k["x1"] <= gap]), _join([k for k in row if k["x0"] >= gap])
        if "Rp" not in left and "rp" not in left.lower():
            return None, "baris tabel tanpa rupiah di kolom kiri"
        written.append(f"{left} {right}".strip())
    outside = [k for k in boxes if k not in table]
    before = _lines([k for k in outside if k["y0"] < top])
    after = _lines([k for k in outside if k["y0"] >= top])
    return "\n".join(before + written + after), f"tabel {len(rates)} baris"


def _find_page(lines: list[str], boxes: list[dict]) -> tuple[int, int] | None:
    filled = [k for k in boxes if k["teks"].strip()]
    want = Counter(k["teks"].strip() for k in filled)
    n = sum(want.values())
    idx = [i for i, x in enumerate(lines) if x.strip()]
    if n == 0 or len(idx) < n:
        return None
    top = min(filled, key=lambda k: (k["y0"], k["x0"]))["teks"].strip()
    bottom = max(filled, key=lambda k: (k["y1"], k["x0"]))["teks"].strip()
    window = Counter(lines[i].strip() for i in idx[:n])
    found = []
    for s in range(len(idx) - n + 1):
        if s:
            window[lines[idx[s - 1]].strip()] -= 1
            window[lines[idx[s + n - 1]].strip()] += 1
        if +window == want and lines[idx[s]].strip() == top and lines[idx[s + n - 1]].strip() == bottom:
            found.append((idx[s], idx[s + n - 1] + 1))
    return found[0] if len(found) == 1 else None


def reflow(text: str, content: bytes, page_texts: list[str] | None = None, ocr=None) -> Reflow:
    out = Reflow(text)
    selected = candidate_pages(content, page_texts)
    if not selected:
        return out
    if ocr is None:
        from .ter_table import ocr_boxes as ocr
    data, err = ocr(content, selected)
    if data is None:
        out.lines.append(f"PERINGATAN: OCR kotak tabel pasal gagal ({err}); teks dibiarkan")
        return out
    for page in data["halaman"]:
        n = page["nomor"]
        new, note = rebuild_page(page)
        if new is None:
            if note not in ("kurang dari dua sel tarif", "halaman kosong"):
                out.lines.append(f"hal {n}: tabel pasal tidak disusun ulang ({note})")
            continue
        lines = out.text.split(NL)
        span = _find_page(lines, page["kotak"])
        if span is None:
            out.lines.append(f"hal {n}: tabel pasal tidak disusun ulang (baris halaman tidak ditemukan tepat sekali "
                             "di teks)")
            continue
        a, b = span
        out.text = NL.join(lines[:a] + new.split(NL) + lines[b:])
        out.pages.append(n)
        out.lines.append(f"hal {n}: tabel pasal disusun ulang dari OCR kotak ({note})")
    return out


def reflow_source(source: SourceText, ocr=None, ocr_dir: Path = OCR_DIR) -> Reflow:
    pdf = source.pdf()
    pages = corpus_pages(source, ocr_dir) if source.source == "jdih" else None
    if pdf is None or pages is None:
        return Reflow(source.text)
    return reflow(source.text, pdf.read_bytes(), pages, ocr)
