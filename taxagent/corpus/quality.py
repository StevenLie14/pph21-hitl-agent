from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

from ..update.amounts import clean_text

MIN_TEXT = 200
JUNK_UNUSABLE = 0.05
MAX_JUNK = 0.005
MAX_UNKNOWN = 20.0
MAX_MIXED = 2.0
MIN_CHARS_PER_PAGE = 300
DF_MIN = 2

_TOKEN = re.compile(r"\w+", re.U)
_PLAUSIBLE_MIXED = re.compile(r"^(\d{1,3}[a-z]|[a-z]\d{1,2}|rp\d+)$")
_BROKEN_NUMBER = re.compile(r"^(?=(?:\D*\d){2})(?=.*[ol])[\dol]{3,}$")
_OPENING = re.compile(r"PASAL 1\b|\bKESATU\b|\bMEMUTUSKAN\b|\bMENETAPKAN\b")
_CLOSING = re.compile(r"DITETAPKAN DI|DIUNDANGKAN DI")


def letter_words(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if len(t) >= 3 and t.isalpha()]


def _is_mixed(token: str) -> bool:
    return any(c.isdigit() for c in token) and any(c.isalpha() for c in token) and not _PLAUSIBLE_MIXED.match(token)


class Vocabulary:
    def __init__(self, reference_texts: Iterable[str]):
        self.df: Counter[str] = Counter()
        self.n = 0
        for t in reference_texts:
            self.df.update(set(letter_words(t)))
            self.n += 1

    def knows(self, word: str, own_words: set[str] | frozenset[str] = frozenset()) -> bool:
        return self.df.get(word, 0) - (word in own_words) >= DF_MIN


@dataclass
class QualityInput:
    key: str
    source: str
    text: str
    number: int | None = None
    year: int | None = None
    pages: int | None = None
    regulation: bool = True


@dataclass
class QualityResult:
    kunci: str
    sumber: str
    status: str
    alasan: list[str] = field(default_factory=list)
    ukuran: dict = field(default_factory=dict)


def check_identity(text: str, number: int | None, year: int | None) -> bool | None:
    if number is None and year is None:
        return None
    head = " ".join(text[:3000].upper().split())
    if year is not None and str(year) not in head:
        return False
    if number is None:
        return True
    n = rf"(?<![\d.])0*{number}(?!\d)"
    return bool(re.search(rf"(?:N\s?O\s?M\s?O\s?R|NOOR|NO\.)\W{{0,3}}.{{0,12}}?{n}", head)
                or re.search(rf"{n}\s*TAHUN\s*{year}", head))


def measure(doc: QualityInput, vocabulary: Vocabulary, own_words: set[str] | frozenset[str] = frozenset()) -> dict:
    text = doc.text or ""
    upper = " ".join(text.upper().split())
    words = letter_words(text)
    token = _TOKEN.findall(text.lower())
    unknown = [k for k in words if not vocabulary.knows(k, own_words)]
    mixed = [t for t in token if _is_mixed(t)]
    junk = text.count("(cid:") * 7 + sum(1 for ch in text if ch == "�" or "" <= ch <= ""
                                         or (ch.isalpha() and ord(ch) > 0x24F))
    b = clean_text(text) if text else None
    return {
        "huruf": len(text),
        "kata": len(words),
        "identitas": check_identity(text, doc.number, doc.year),
        "pembuka": bool(_OPENING.search(upper)),
        "penutup": bool(_CLOSING.search(upper)),
        "huruf_per_halaman": round(len(text) / doc.pages) if doc.pages else None,
        "angka_tidak_cocok": len(b.mismatches) if b else 0,
        "angka_terverifikasi": len(b.verified) if b else 0,
        "angka_tanpa_terbilang": len(b.without_words) if b else 0,
        "angka_rusak": sum(1 for t in token if _BROKEN_NUMBER.match(t)),
        "asing_per_1000": round(1000 * len(unknown) / len(words), 2) if words else 0.0,
        "campuran_per_1000": round(1000 * len(mixed) / len(token), 2) if token else 0.0,
        "sampah": round(junk / len(text), 4) if text else 0.0,
        "contoh_asing": [k for k, _ in Counter(unknown).most_common(8)],
        "contoh_campuran": [k for k, _ in Counter(mixed).most_common(8)],
        "contoh_angka": (b.mismatches[:3] if b else []) + sorted({t for t in token if _BROKEN_NUMBER.match(t)})[:3],
    }


def decide(doc: QualityInput, u: dict) -> tuple[str, list[str]]:
    if u["huruf"] < MIN_TEXT:
        return "tidak_terpakai", [f"teks kosong ({u['huruf']} huruf)"]
    if u["sampah"] > JUNK_UNUSABLE:
        return "tidak_terpakai", [f"{u['sampah']:.1%} karakter sampah (font rusak / encoding)"]
    reasons = []
    if u["angka_tidak_cocok"]:
        reasons.append(f"{u['angka_tidak_cocok']} angka tidak cocok dengan terbilang")
    if u["angka_rusak"]:
        reasons.append(f"{u['angka_rusak']} angka rusak (huruf o/l di antara digit)")
    if u["identitas"] is False:
        reasons.append(f"nomor {doc.number} / tahun {doc.year} tidak ditemukan di kepala teks")
    if doc.regulation and doc.source != "pajak" and not (u["pembuka"] and u["penutup"]):
        reasons.append("tanpa " + " dan ".join(x for x, present in (("pembuka", u["pembuka"]), ("penutup", u["penutup"]))
                                               if not present))
    if u["huruf_per_halaman"] is not None and u["huruf_per_halaman"] < MIN_CHARS_PER_PAGE:
        reasons.append(f"{u['huruf_per_halaman']} huruf per halaman (halaman tidak terbaca?)")
    if u["asing_per_1000"] > MAX_UNKNOWN:
        reasons.append(f"{u['asing_per_1000']} kata tak dikenal per 1.000")
    if u["campuran_per_1000"] > MAX_MIXED:
        reasons.append(f"{u['campuran_per_1000']} kata campuran huruf-angka per 1.000")
    if u["sampah"] > MAX_JUNK:
        reasons.append(f"{u['sampah']:.2%} karakter sampah")
    return ("perlu_dicek" if reasons else "andal"), reasons


def assess(doc: QualityInput, vocabulary: Vocabulary, own_words: set[str] | frozenset[str] = frozenset()) -> QualityResult:
    u = measure(doc, vocabulary, own_words)
    status, reasons = decide(doc, u)
    return QualityResult(doc.key, doc.source, status, reasons, u)


_SWAPS = {"l": "1", "1": "l", "i": "l", "I": "l", "O": "0", "0": "O", "o": "0", "m": "rn", "n": "ri", "e": "c", "a": "o"}


def noise(text: str, rate: float, seed: int = 0) -> str:
    import random

    rng = random.Random(seed)
    words = text.split(" ")
    out: list[str] = []
    i = 0
    while i < len(words):
        w = words[i]
        if w and rng.random() < rate:
            kind = rng.randrange(3)
            if kind == 0:
                positions = [j for j, ch in enumerate(w) if ch in _SWAPS]
                if positions:
                    j = rng.choice(positions)
                    w = w[:j] + _SWAPS[w[j]] + w[j + 1:]
            elif kind == 1 and i + 1 < len(words):
                w = w + words[i + 1]
                i += 1
            elif len(w) > 3:
                j = rng.randrange(1, len(w) - 1)
                w = w[:j] + " " + w[j:]
        out.append(w)
        i += 1
    return " ".join(out)
