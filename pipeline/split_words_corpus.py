from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from taxagent.corpus.word_split import MIN_LENGTH, Lexicon, split_text  # noqa: E402
from taxagent.paths import DATA  # noqa: E402

JDIH_DIR = DATA / "korpus_jdih"
_RE_LONG_WORD = re.compile(rf"(?<![A-Za-z0-9])[A-Za-z]{{{MIN_LENGTH},}}(?![A-Za-z0-9])")


def _quality(d: Path) -> list[dict]:
    return [json.loads(b) for b in (d / "mutu.jsonl").read_text(encoding="utf-8").splitlines()]


def _text(d: Path, key: str) -> str:
    return (d / "teks" / f"{key}.txt").read_text(encoding="utf-8")


def _reliable(d: Path, sources: tuple[str, ...]) -> list[str]:
    return [x["kunci"] for x in _quality(d) if x["sumber"] in sources and x["status"] == "andal"]


def cmd_lexicon(a) -> None:
    ids = _reliable(a.dir, ("jdih_htm", "jdih_digital"))
    lex = Lexicon.from_texts(_text(a.dir, i) for i in ids)
    lex.save(a.dir / "kamus_pecah.json")
    print(f"{len(ids)} dokumen andal -> {len(lex.freq)} kata, {len(lex.bigram)} pasangan: {a.dir / 'kamus_pecah.json'}")


def _boundaries(words: list[str]) -> set[int]:
    pos, result = 0, set()
    for w in words[:-1]:
        pos += len(w)
        result.add(pos)
    return result


def cmd_synthetic(a) -> None:
    lex = Lexicon.from_texts(_text(a.dir, i) for i in _reliable(a.dir, ("jdih_htm",)))
    test = _reliable(a.dir, ("jdih_digital",))
    rng = random.Random(a.seed)
    sample = rng.sample(test, min(a.n, len(test)))
    removed = restored = restored_eligible = eligible = spurious = 0
    spurious_examples: list[str] = []
    for i in sample:
        for line in _text(a.dir, i).splitlines():
            words = line.split()
            if len(words) < 2 or not all(w.isalpha() for w in words):
                continue
            joined, dropped = [words[0]], set()
            pos = len(words[0])
            for w in words[1:]:
                if rng.random() < a.rate:
                    joined[-1] += w
                    dropped.add(pos)
                else:
                    joined.append(w)
                pos += len(w)
            if not dropped:
                continue
            original, broken = _boundaries(words), _boundaries(joined)
            output = _boundaries(split_text(" ".join(joined), lex)[0].split())
            new = output - broken
            removed += len(dropped)
            restored += len(new & dropped)
            spurious += len(new - original)
            pos = 0
            for t in joined:
                inside = {b for b in dropped if pos < b < pos + len(t)}
                if inside and len(t) >= MIN_LENGTH:
                    eligible += len(inside)
                    restored_eligible += len(inside & new)
                pos += len(t)
            if new - original and len(spurious_examples) < 10:
                spurious_examples.append(split_text(" ".join(joined), lex)[0][:160])
    correct = restored
    print(f"sampel {len(sample)} PDF digital andal, spasi dihapus {a.rate:.0%}: {removed} batas dihapus")
    print(f"dipulihkan {restored} ({restored / max(1, removed):.1%}); dari yang layak (token gabungan >= {MIN_LENGTH} "
          f"huruf) {restored_eligible}/{eligible} ({restored_eligible / max(1, eligible):.1%})")
    print(f"spasi palsu {spurious}; presisi {correct / max(1, correct + spurious):.2%}")
    for c in spurious_examples:
        print("  palsu?", c)


def cmd_ocr(a) -> None:
    lex = Lexicon.load(a.dir / "kamus_pecah.json")
    ids = [x["kunci"] for x in _quality(a.dir) if x["sumber"] == "jdih_ocr"]
    words = unknown_before = unknown_after = split = 0
    examples: list[tuple[str, str]] = []
    rng = random.Random(a.seed)
    for i in ids:
        t = _text(a.dir, i)
        new, n = split_text(t, lex)
        split += n
        words += len(t.split())
        unknown_before += sum(1 for w in _RE_LONG_WORD.findall(t) if not lex.knows(w))
        unknown_after += sum(1 for w in _RE_LONG_WORD.findall(new) if not lex.knows(w))
        if n and rng.random() < 0.05 and len(examples) < a.examples:
            old = [w for w in _RE_LONG_WORD.findall(t) if not lex.knows(w)]
            for w in old:
                p = split_text(w, lex)[0]
                if p != w:
                    examples.append((w, p))
                    break
    print(f"{len(ids)} dokumen OCR, {words} kata; {split} kata tergabung dipecah "
          f"({split / max(1, words) * 1000:.1f} per 1.000)")
    print(f"kata panjang tak dikenal per 1.000: {unknown_before / max(1, words) * 1000:.2f} -> "
          f"{unknown_after / max(1, words) * 1000:.2f}")
    for w, p in examples:
        print(f"  {w} -> {p}")


def main() -> None:
    ap = argparse.ArgumentParser(description='Lexicon for splitting joined words (``taxagent.corpus.word_split``) and its measurement.')
    ap.add_argument("--dir", type=Path, default=JDIH_DIR)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("lexicon").set_defaults(func=cmd_lexicon)
    p = sub.add_parser("synthetic")
    p.add_argument("--n", type=int, default=200)
    p.add_argument("--rate", dest="rate", type=float, default=0.03)
    p.add_argument("--seed", type=int, default=1)
    p.set_defaults(func=cmd_synthetic)
    p = sub.add_parser("ocr")
    p.add_argument("--examples", dest="examples", type=int, default=40)
    p.add_argument("--seed", type=int, default=1)
    p.set_defaults(func=cmd_ocr)
    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
