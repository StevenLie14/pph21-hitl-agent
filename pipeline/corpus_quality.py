from __future__ import annotations

import argparse
import collections
import dataclasses
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from taxagent.corpus.quality import QualityInput, Vocabulary, assess, letter_words, noise  # noqa: E402
from taxagent.paths import DATA  # noqa: E402

JDIH_DIR = DATA / "korpus_jdih"
PAJAK_DIR = DATA / "korpus_pajak"
_REGULATION_FORMS = ("Peraturan", "Keputusan", "Undang", "Instruksi")


def _read(f: Path) -> dict:
    return json.loads(f.read_text(encoding="utf-8"))


def _int(x) -> int | None:
    try:
        return int(x) if x not in (None, "", 0) else None
    except (TypeError, ValueError):
        return None


def jdih_documents(d: Path) -> list[QualityInput]:
    listing: dict[str, dict] = {}
    for f in sorted((d / "daftar").glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            x = json.loads(line)
            listing.setdefault(x["produk_hukum_id"], x)
    result = []
    for f in (d / "teks").glob("*.txt"):
        b = d / "berkas" / f"{f.stem}.json"
        if not b.exists():
            continue
        record, meta = _read(b), listing.get(f.stem, {})
        source = {"digital": "jdih_digital", "scan": "jdih_ocr", "htm": "jdih_htm"}.get(record.get("jenis"))
        if source is None:
            continue
        result.append(QualityInput(f.stem, source, f.read_text(encoding="utf-8"), _int(meta.get("no")),
                                   _int(meta.get("tahun")), record.get("halaman"),
                                   str(meta.get("bentuk", "")).startswith(_REGULATION_FORMS)))
    return result


def pajak_documents(d: Path) -> list[QualityInput]:
    result = []
    for f in (d / "teks").glob("*.txt") if (d / "teks").exists() else []:
        det = _read(d / "detail" / f"{f.stem}.json")
        number = det.get("nomor", "")
        digits = re.findall(r"\d+", number)
        years = re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", number)
        result.append(QualityInput(f.stem, "pajak", f.read_text(encoding="utf-8"), int(digits[0]) if digits else None,
                                   int(years[-1]) if years else None, None,
                                   str(det.get("jenis", "")).startswith(_REGULATION_FORMS)))
    return result


def _vocabulary(jdih: list[QualityInput]) -> Vocabulary:
    reference = [x.text for x in jdih if x.source == "jdih_digital"]
    print(f"kosakata acuan: {len(reference)} PDF digital", flush=True)
    return Vocabulary(reference)


def cmd_assess(a: argparse.Namespace) -> None:
    jdih, pajak = jdih_documents(a.jdih), pajak_documents(a.pajak)
    vocab = _vocabulary(jdih)
    counts: collections.Counter = collections.Counter()
    reasons: collections.Counter = collections.Counter()
    for corpus, docs in ((a.jdih, jdih), (a.pajak, pajak)):
        if not docs:
            continue
        with open(corpus / "mutu.jsonl", "w", encoding="utf-8") as f:
            for x in docs:
                own = set(letter_words(x.text)) if x.source == "jdih_digital" else frozenset()
                h = assess(x, vocab, own)
                f.write(json.dumps(dataclasses.asdict(h), ensure_ascii=False) + "\n")
                counts[(h.sumber, h.status)] += 1
                reasons.update(re.sub(r"[\d.,%]+", "N", s) for s in h.alasan)
    print(f"\n{'sumber':14} {'andal':>7} {'perlu_dicek':>12} {'tidak_terpakai':>15}")
    for s in sorted({s for s, _ in counts}):
        print(f"{s:14} {counts[s, 'andal']:7d} {counts[s, 'perlu_dicek']:12d} {counts[s, 'tidak_terpakai']:15d}")
    print("\nalasan terbanyak:")
    for s, n in reasons.most_common(15):
        print(f"  {n:6d}  {s}")


def cmd_noise(a: argparse.Namespace) -> None:
    jdih = jdih_documents(a.jdih)
    vocab = _vocabulary(jdih)
    reliable = [x for x in jdih if x.source == "jdih_digital"
                and assess(x, vocab, set(letter_words(x.text))).status == "andal"]
    sample = random.Random(a.seed).sample(reliable, min(a.n, len(reliable)))
    print(f"{len(reliable)} PDF digital andal, sampel {len(sample)}")
    for rate in (0.01, 0.03, 0.08):
        status: collections.Counter = collections.Counter()
        for i, x in enumerate(sample):
            broken = dataclasses.replace(x, teks=noise(x.text, rate, seed=a.seed + i))
            status[assess(broken, vocab, set(letter_words(x.text))).status] += 1
        caught = len(sample) - status["andal"]
        print(f"derau {rate:.0%}: tertangkap {caught}/{len(sample)} ({caught / max(1, len(sample)):.1%}) "
              f"{dict(status)}")


def main() -> None:
    ap = argparse.ArgumentParser(description='Stage 3: text quality check of the whole corpus (``taxagent.corpus.quality``) and a robustness test with')
    ap.add_argument("--jdih", type=Path, default=JDIH_DIR)
    ap.add_argument("--pajak", type=Path, default=PAJAK_DIR)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("assess").set_defaults(func=cmd_assess)
    p = sub.add_parser("noise")
    p.add_argument("--n", type=int, default=200)
    p.add_argument("--seed", type=int, default=1000)
    p.set_defaults(func=cmd_noise)
    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
