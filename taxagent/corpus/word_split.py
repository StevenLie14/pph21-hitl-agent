from __future__ import annotations

import collections
import json
import math
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

MIN_LENGTH = 8
MIN_FREQ = 20
MIN_BIGRAM = 2
MAX_PARTS = 4
SHORT_WORDS = frozenset({"di", "ke", "dan", "atau", "dari", "yang", "pada", "oleh", "atas", "per"})
_RE_WORD = re.compile(r"[A-Za-z]+")
_RE_LETTER_TOKEN = re.compile(rf"(?<![A-Za-z0-9])[A-Za-z]{{{MIN_LENGTH},}}(?![A-Za-z0-9])")


@dataclass
class Lexicon:
    freq: dict[str, int]
    bigram: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_texts(cls, texts: Iterable[str], min_freq: int = 3) -> Lexicon:
        uni: collections.Counter = collections.Counter()
        bi: collections.Counter = collections.Counter()
        for t in texts:
            for line in t.lower().splitlines():
                words = _RE_WORD.findall(line)
                uni.update(words)
                bi.update(f"{a} {b}" for a, b in zip(words, words[1:]) if len(a) + len(b) >= MIN_LENGTH)
        return cls({w: c for w, c in uni.items() if c >= min_freq},
                   {k: c for k, c in bi.items() if c >= MIN_BIGRAM})

    def save(self, path: Path) -> None:
        Path(path).write_text(json.dumps({"frek": self.freq, "bigram": self.bigram}, ensure_ascii=False),
                              encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> Lexicon:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(d["frek"], d["bigram"])

    def knows(self, word: str) -> bool:
        return word.lower() in self.freq


def _valid_part(k: Lexicon, w: str) -> bool:
    return (len(w) >= 3 or w in SHORT_WORDS) and k.freq.get(w, 0) >= (1 if w in SHORT_WORDS else MIN_FREQ)


def split_word(word: str, k: Lexicon) -> list[str] | None:
    w = word.lower()
    if len(w) < MIN_LENGTH or not w.isalpha() or w in k.freq:
        return None
    total = sum(k.freq.values()) or 1
    n = len(w)
    best: list[tuple[float, int, list[str]] | None] = [None] * (n + 1)
    best[0] = (0.0, 0, [])
    for i in range(1, n + 1):
        for j in range(max(0, i - 30), i):
            if best[j] is None:
                continue
            part = w[j:i]
            if not _valid_part(k, part):
                continue
            cost, count, parts = best[j]
            candidate = (cost - math.log(k.freq[part] / total), count + 1, parts + [part])
            if candidate[1] <= MAX_PARTS and (best[i] is None or candidate[0] < best[i][0]):
                best[i] = candidate
    result = best[n]
    if result is None or result[1] < 2:
        return None
    parts = result[2]
    if any(k.bigram.get(f"{a} {b}", 0) < MIN_BIGRAM for a, b in zip(parts, parts[1:])):
        return None
    return parts


def split_text(text: str, k: Lexicon) -> tuple[str, int]:
    count = 0

    def replace(m: re.Match) -> str:
        nonlocal count
        original = m.group(0)
        parts = split_word(original, k)
        if parts is None:
            return original
        count += 1
        out, pos = [], 0
        for b in parts:
            out.append(original[pos:pos + len(b)])
            pos += len(b)
        return " ".join(out)

    return _RE_LETTER_TOKEN.sub(replace, text), count
