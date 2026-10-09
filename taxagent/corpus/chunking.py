from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

TARGET, MIN, MAX = 1500, 300, 2500
_RE_TITLE_LINE = re.compile(r"(?m)^[ \t]*(?:Pasal|PASAL)[ \t]+(\d+[A-Z]?|[IVX]+)[ \t]*$")
_RE_TITLE = re.compile(r"(?<![a-z] )(?<![a-z],)(?<![a-z]\()(?<![A-Z] )\b(?:Pasal|PASAL)\s+(\d+[A-Z]?|[IVX]+)\s+"
                       r"(?=[A-Z(]|[a-z]\. )")
_RE_DICTUM = re.compile(r"(?m)^\s*(KESATU|KEDUA|KETIGA|KEEMPAT|KELIMA|KEENAM|KETUJUH|KEDELAPAN|KESEMBILAN|"
                        r"KESEPULUH|KESEBELAS|KEDUA BELAS|KETIGA BELAS)\s*:")
_RE_DECIDING = re.compile(r"\bMEMUTUSKAN\b|\bMemutuskan\s*:")
_RE_CLOSING = re.compile(r"Agar\s+setiap\s+(?:\S{1,2}\s+)?orang\s+(?:\S{1,2}\s+)?mengetahuinya"
                         r"|memerintahkan\s+pengundangan", re.I)
_RE_PARAGRAPH = re.compile(r"(?<=\s)\(\d{1,2}\)\s")


@dataclass
class Chunk:
    order: int
    label: str
    start: int
    end: int
    text: str


def _split_even(text: str, start: int, end: int, label: str) -> list[tuple[str, int, int]]:
    result, i = [], start
    while i < end:
        j = min(end, i + TARGET)
        if j < end:
            sp = text.rfind(" ", i + TARGET // 2, j)
            j = sp if sp > i else j
        result.append((label, i, j))
        i = j
    return result


def _split_paragraphs(text: str, start: int, end: int, label: str) -> list[tuple[str, int, int]]:
    bounds, expected = [], 1
    for m in _RE_PARAGRAPH.finditer(text, start, end):
        if int(text[m.start() + 1:m.end()].split(")")[0]) == expected:
            bounds.append(m.start())
            expected += 1
    if len(bounds) < 2:
        return _split_even(text, start, end, label)
    points = [start] + [b for b in bounds if b > start] + [end]
    result, cursor = [], points[0]
    for k in range(1, len(points)):
        if points[k] - cursor >= TARGET or k == len(points) - 1:
            result.append((cursor, points[k]))
            cursor = points[k]
    out = []
    for a, b in result:
        paragraphs = [m.group(1) for x in bounds if a <= x < b and (m := re.match(r"\((\d{1,2})\)", text[x:x + 5]))]
        lab = f"{label} ayat ({paragraphs[0]})-({paragraphs[-1]})" if len(paragraphs) > 1 else \
            (f"{label} ayat ({paragraphs[0]})" if paragraphs else label)
        out += _split_even(text, a, b, lab) if b - a > MAX * 2 else [(lab, a, b)]
    return out


def chunk(text: str) -> list[Chunk]:
    if not text.strip():
        return []
    m = _RE_DECIDING.search(text)
    body_start = m.end() if m else 0
    g = _RE_CLOSING.search(text, body_start)
    body_end = g.start() if g else len(text)
    spans: list[tuple[str, int, int]] = []
    if body_start > 0:
        spans += _split_even(text, 0, body_start, "Pembukaan") if body_start > MAX * 2 else [("Pembukaan", 0, body_start)]
    titles = [(f"Pasal {x.group(1)}", x.start()) for x in _RE_TITLE_LINE.finditer(text, body_start, body_end)]
    if len(titles) < 2:
        titles = [(f"Pasal {x.group(1)}", x.start()) for x in _RE_TITLE.finditer(text, body_start, body_end)]
    if len(titles) < 2:
        titles = [(f"Diktum {x.group(1).title()}", x.start()) for x in _RE_DICTUM.finditer(text, body_start, body_end)]
    if len(titles) >= 2:
        if titles[0][1] > body_start + 20:
            spans.append(("Penetapan", body_start, titles[0][1]))
        units = [(lab, a, titles[k + 1][1] if k + 1 < len(titles) else body_end) for k, (lab, a) in enumerate(titles)]
        k = 0
        while k < len(units):
            lab, a, b = units[k]
            last_number = None
            while b - a < MIN and k + 1 < len(units) and units[k + 1][2] - a <= TARGET:
                k += 1
                b, last_number = units[k][2], units[k][0].split(" ", 1)[1]
            if last_number:
                lab = f"{lab}-{last_number}"
            spans += _split_paragraphs(text, a, b, lab) if b - a > MAX else [(lab, a, b)]
            k += 1
    else:
        spans += _split_even(text, body_start, body_end, "Batang tubuh")
    if body_end < len(text):
        spans += _split_even(text, body_end, len(text), "Lampiran")
    return [Chunk(i, lab, a, b, text[a:b]) for i, (lab, a, b) in enumerate(spans) if text[a:b].strip()]


def search_text(name: str, titles: str, label: str, content: str, split: Callable[[str], str] | None = None) -> str:
    header = f"{name}, {titles}. {label}." if titles else f"{name}. {label}."
    content = " ".join(content.split())
    return f"{header} {split(content) if split else content}"
