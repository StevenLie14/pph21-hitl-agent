from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

_UNITS = {
    "NOL": 0, "SATU": 1, "SE": 1, "DUA": 2, "TIGA": 3, "EMPAT": 4, "LIMA": 5,
    "ENAM": 6, "TUJUH": 7, "DELAPAN": 8, "SEMBILAN": 9, "SEPULUH": 10, "SEBELAS": 11,
}
_SCALES = {"RIBU": 10**3, "JUTA": 10**6, "MILIAR": 10**9, "MILYAR": 10**9, "TRILIUN": 10**12}


def parse_terbilang(text: str) -> Decimal | None:
    words = re.sub(r"[^A-Z ]", " ", text.upper()).split()
    parts: list[str] = []
    for k in words:
        if k in ("SERATUS", "SERIBU", "SEJUTA", "SEPULUH", "SEBELAS"):
            parts += [k] if k in _UNITS else ["SE", k[2:]]
        elif k.startswith("SE") and k[2:] in ("BELAS", "RATUS", "RIBU", "JUTA"):
            parts += ["SE", k[2:]]
        else:
            parts.append(k)
    if "KOMA" in parts:
        i = parts.index("KOMA")
        whole, fraction = parts[:i], parts[i + 1:]
        b = _whole(whole) if whole else 0
        if b is None or not fraction or any(k not in _UNITS for k in fraction):
            return None
        return Decimal(str(b)) + Decimal("0." + "".join(str(_UNITS[k]) for k in fraction))
    b = _whole(parts)
    return None if b is None else Decimal(b)


def _whole(words: list[str]) -> int | None:
    total = group = digit = 0
    for k in words:
        if k in _UNITS:
            digit += _UNITS[k]
        elif k == "BELAS":
            digit += 10
        elif k == "PULUH":
            group += digit * 10
            digit = 0
        elif k == "RATUS":
            group += digit * 100
            digit = 0
        elif k in _SCALES:
            total += (group + digit) * _SCALES[k]
            group = digit = 0
        else:
            return None
    return total + group + digit


def parse_rupiah(digit: str) -> Decimal:
    s = digit.replace(" ", "")
    whole, _, cents = s.partition(",")
    return Decimal(whole.replace(".", "") + ("." + cents if cents.strip("0") else ""))


def parse_percent(digit: str) -> Decimal:
    return Decimal(digit.replace(" ", "").replace(",", "."))


@dataclass
class CleanText:
    text: str
    mismatches: list[str] = field(default_factory=list)
    verified: set[Decimal] = field(default_factory=set)
    without_words: set[Decimal] = field(default_factory=set)


_RE_RP = re.compile(r"RP\s*\.?\s*(\d{1,3}(?:\s?\.\s?\d{3})+(?:\s?,\s?\d{1,2})?|\d+(?:,\d{1,2})?)\s*(\(\s*\(?[A-Z\s]+?RUPIAH\s*[),]?)?")
_RE_PERCENT = re.compile(r"(\d+(?:\s?,\s?\d+)?)\s?%\s*(\(\s*[A-Z\s]+?PERSEN\s*\))?")


def clean_text(text: str) -> CleanText:
    t = re.sub(r"\s+", " ", text.upper())
    t = re.sub(r"(\d)\s?\.\s?,\s?(\d{2})(?!\d)", r"\1,\2", t)
    result = CleanText("")

    def record(value: Decimal, words: Decimal | None) -> None:
        (result.verified if words == value else result.without_words).add(value)

    def replace_rp(m: re.Match) -> str:
        value = parse_rupiah(m.group(1))
        words = parse_terbilang(re.sub(r"RUPIAH.*", "", m.group(2))) if m.group(2) else None
        if words is not None and words != value:
            result.mismatches.append(f"Rp{m.group(1)} tetapi terbilang {m.group(2).strip()} = {words}")
            return f" RP?{_text(value)} "
        record(value, words)
        return f" RP{_text(value)} "

    def replace_percent(m: re.Match) -> str:
        value = parse_percent(m.group(1))
        words = parse_terbilang(re.sub(r"PERSEN.*", "", m.group(2))) if m.group(2) else None
        if words is not None and words != value:
            result.mismatches.append(f"{m.group(1)}% tetapi terbilang {m.group(2).strip()} = {words}")
            return f" ?{_text(value)}% "
        record(value, words)
        return f" {_text(value)}% "

    t = _RE_RP.sub(replace_rp, t)
    t = _RE_PERCENT.sub(replace_percent, t)
    for m in _RE_REST.finditer(t):
        token, words = m.group(1), parse_terbilang(m.group(2))
        if words is None or not any(ch.isdigit() for ch in token):
            continue
        if (m.group(3) == "PERSEN" and token.startswith("RP")) or (m.group(3) == "RUPIAH" and token.endswith("%")):
            continue
        value = _number_token(token, m.group(3))
        if value == words:
            result.verified.add(value)
        else:
            result.mismatches.append(f"{token} tetapi terbilang ({m.group(2).strip()} {m.group(3)}) = {words}")
    for m in _RE_NUMBER_WORDS.finditer(t):
        value, words = Decimal(m.group(1)), parse_terbilang(m.group(2))
        if words is None:
            continue
        if words != value:
            result.mismatches.append(f"{m.group(1)} tetapi terbilang ({m.group(2).strip()}) = {words}")
        else:
            result.verified.add(value)
    result.text = re.sub(r"\s+", " ", t).strip()
    return result


_RE_NUMBER_WORDS = re.compile(r"(?<![\d.,?])(\d{1,4})\s*\(\s*([A-Z][A-Z ]*?)\s*\)")
_RE_REST = re.compile(r"(\S+)\s*\(\s*\(?([A-Z][A-Z ]*?)\s*(RUPIAH|PERSEN)\s*[),]")


def _number_token(token: str, unit: str) -> Decimal | None:
    s = token.strip("(),;:")
    if unit == "RUPIAH":
        s = s[2:] if s.startswith("RP") else s
        s = s.lstrip(".")
    else:
        s = s.rstrip("%")
    try:
        return parse_rupiah(s) if unit == "RUPIAH" else parse_percent(s)
    except (ArithmeticError, ValueError):
        return None


def _text(d: Decimal) -> str:
    s = format(d.normalize(), "f")
    return s


_WORDS = ["", "satu", "dua", "tiga", "empat", "lima", "enam", "tujuh", "delapan", "sembilan", "sepuluh", "sebelas"]


def _whole_words(n: int) -> str:
    if n < 12:
        return _WORDS[n]
    if n < 20:
        return f"{_WORDS[n - 10]} belas"
    if n < 100:
        return f"{_WORDS[n // 10]} puluh {_whole_words(n % 10)}".strip()
    if n < 1000:
        head = "seratus" if n // 100 == 1 else f"{_WORDS[n // 100]} ratus"
        return f"{head} {_whole_words(n % 100)}".strip()
    for scale, name in ((10**12, "triliun"), (10**9, "miliar"), (10**6, "juta"), (10**3, "ribu")):
        if n >= scale:
            head = "seribu" if scale == 1000 and n // scale == 1 else f"{_whole_words(n // scale)} {name}"
            return f"{head} {_whole_words(n % scale)}".strip()
    raise AssertionError(n)


def to_terbilang(d: Decimal | int) -> str:
    d = Decimal(d)
    whole = int(d)
    text = _whole_words(whole) if whole else "nol"
    fraction = format(d - whole, "f").partition(".")[2].rstrip("0")
    if fraction:
        text += " koma " + " ".join(_WORDS[int(c)] if c != "0" else "nol" for c in fraction)
    return text


def format_rupiah(d: Decimal | int) -> str:
    return "Rp" + f"{int(d):,}".replace(",", ".") + ",00"


def yaml_number(d: Decimal):
    return int(d) if d == d.to_integral_value() else float(d)
