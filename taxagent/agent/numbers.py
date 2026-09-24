from __future__ import annotations

import re
from typing import Any

_SCALE_AHEAD = r"(?!\d|[.,]\d|\s*(?:miliar|milyar|juta|jt|ribu|rb)\b)"
_RE_AMOUNT = re.compile(rf"(?i)(?:rp\.?\s*)(\d{{1,3}}(?:\.\d{{3}})+|\d+)(?:,\d+)?{_SCALE_AHEAD}"
                        rf"|\b(\d{{1,3}}(?:\.\d{{3}}){{1,}})(?:,\d+)?\b{_SCALE_AHEAD}")
_RE_WORDS = re.compile(r"(?i)(?:\brp\.?\s*|\b)(\d{1,3}(?:\.\d{3})+|\d+(?:[.,]\d+)?)\s*(miliar|milyar|juta|jt|ribu|rb)\b")
_RE_THOUSANDS = re.compile(r"\d{1,3}(?:\.\d{3})+")
_SCALE = {"miliar": 10**9, "milyar": 10**9, "juta": 10**6, "jt": 10**6, "ribu": 10**3, "rb": 10**3}


def amounts(text: str) -> set[int]:
    found = set()
    for m in _RE_AMOUNT.finditer(text or ""):
        v = int((m.group(1) or m.group(2)).replace(".", ""))
        if v >= 1000:
            found.add(v)
    return found


def spoken_amounts(text: str) -> set[int]:
    found = set()
    for m in _RE_WORDS.finditer(text or ""):
        digits = m.group(1)
        number = digits.replace(".", "") if _RE_THOUSANDS.fullmatch(digits) else digits.replace(",", ".")
        found.add(round(float(number) * _SCALE[m.group(2).lower()]))
    return found


def numbers_in(value: Any) -> set[int]:
    if isinstance(value, bool):
        return set()
    if isinstance(value, (int, float)):
        return {round(value)}
    if isinstance(value, str):
        return amounts(value) | spoken_amounts(value) | {int(x) for x in re.findall(r"\b\d{4,}\b", value)}
    if isinstance(value, dict):
        return set().union(*(numbers_in(v) for v in value.values())) if value else set()
    if isinstance(value, (list, tuple)):
        return set().union(*(numbers_in(v) for v in value)) if value else set()
    return set()


def unsourced(answer: str, sources: set[int]) -> list[int]:
    found = amounts(answer) | spoken_amounts(answer)
    return sorted(v for v in found if v >= 1000 and not ({v - 1, v, v + 1} & sources))
