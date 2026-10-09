from __future__ import annotations

import argparse
import collections
import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from taxagent.corpus.merge import DOUBT_SIMILARITY, IndexEntry, SourceDoc, check_doubtful, merge_sources  # noqa: E402
from taxagent.paths import DATA  # noqa: E402

JDIH_DIR = DATA / "korpus_jdih"
PAJAK_DIR = DATA / "korpus_pajak"
MERGED_DIR = DATA / "korpus_gabung"


def _quality(d: Path) -> dict[str, str]:
    f = d / "mutu.jsonl"
    if not f.exists():
        return {}
    return {(h := json.loads(b))["kunci"]: h["status"] for b in f.read_text(encoding="utf-8").splitlines() if b}


def _int(x) -> int | None:
    try:
        return int(x) or None
    except (TypeError, ValueError):
        return None


def jdih_input(d: Path) -> list[SourceDoc]:
    listing: dict[str, dict] = {}
    for f in sorted((d / "daftar").glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            x = json.loads(line)
            listing.setdefault(x["produk_hukum_id"], x)
    texts, quality = {f.stem for f in (d / "teks").glob("*.txt")}, _quality(d)
    return [SourceDoc("jdih", i, x.get("bentuk") or "", x.get("nomor") or "", x.get("judul") or "",
                      _int(x.get("tahun")), i in texts, quality.get(i)) for i, x in listing.items()]


def pajak_input(d: Path) -> list[SourceDoc]:
    f = d / "daftar.jsonl"
    if not f.exists():
        return []
    texts = {f.stem for f in (d / "teks").glob("*.txt")} if (d / "teks").exists() else set()
    quality, result, seen = _quality(d), [], set()
    for line in f.read_text(encoding="utf-8").splitlines():
        x = json.loads(line)
        if x["slug"] in seen:
            continue
        seen.add(x["slug"])
        result.append(SourceDoc("pajak", x["slug"], x["jenis"], x["nomor"], x["judul"], _int(x["tanggal"][:4]),
                                x["slug"] in texts, quality.get(x["slug"])))
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description='Stage 2: merge the JDIH and pajak.go.id corpora into one index (``taxagent.corpus.merge``).')
    ap.add_argument("--jdih", type=Path, default=JDIH_DIR)
    ap.add_argument("--pajak", type=Path, default=PAJAK_DIR)
    ap.add_argument("--out", dest="out", type=Path, default=MERGED_DIR)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    jdih, pajak = jdih_input(a.jdih), pajak_input(a.pajak)
    index, counts = merge_sources(jdih, pajak)
    folder = {"jdih": a.jdih, "pajak": a.pajak}

    def _text(source: str, i: str) -> str | None:
        p = folder[source] / "teks" / f"{i}.txt"
        return p.read_text(encoding="utf-8") if p.exists() else None

    pajak_docs = {m.id: m for m in pajak}
    pajak_entries = {e.id: e for e in index if e.sumber == "pajak"}
    decisions = collections.Counter()
    for e in index:
        if not (e.sumber == "jdih" and e.pasangan and e.kemiripan_judul is not None
                and e.kemiripan_judul < DOUBT_SIMILARITY and (tj := _text("jdih", e.id))):
            continue
        mp = pajak_docs[e.pasangan]
        p = pajak_entries.get(mp.id) or IndexEntry("pajak", mp.id, e.kunci, mp.kind, mp.number, mp.title, mp.year,
                                                   mp.quality, pasangan=e.id)
        tp = _text("pajak", mp.id) if mp.quality != "tidak_terpakai" else None
        decisions[check_doubtful(e, p, tj, tp)] += 1
    counts["ragu_keputusan"] = dict(decisions)

    with open(a.out / "indeks.jsonl", "w", encoding="utf-8") as f, \
            open(a.out / "ragu.jsonl", "w", encoding="utf-8") as fr:
        for e in index:
            line = dataclasses.asdict(e)
            p = folder[e.sumber] / "teks" / f"{e.id}.txt"
            line["teks"] = str(p) if p.exists() and "tanpa teks" not in e.catatan else None
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
            if e.sumber == "jdih" and e.kemiripan_judul is not None and e.kemiripan_judul < DOUBT_SIMILARITY:
                fr.write(json.dumps(line, ensure_ascii=False) + "\n")
    counts["indeks"] = len(index)
    counts["indeks_berteks"] = sum(1 for e in index if "tanpa teks" not in e.catatan)
    counts["per_sumber"] = dict(collections.Counter(e.sumber for e in index if "tanpa teks" not in e.catatan))
    counts["ragu"] = sum(1 for e in index if e.sumber == "jdih" and e.kemiripan_judul is not None
                         and e.kemiripan_judul < DOUBT_SIMILARITY)
    (a.out / "laporan.json").write_text(json.dumps(counts, indent=1), encoding="utf-8")
    for k, v in counts.items():
        print(f"{k:22} {v}")


if __name__ == "__main__":
    main()
