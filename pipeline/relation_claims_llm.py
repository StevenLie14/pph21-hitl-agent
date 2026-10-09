from __future__ import annotations

import argparse
import collections
import concurrent.futures
import json
import random
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from taxagent.cli._common import llm_client  # noqa: E402
from taxagent.corpus.claim_verify import (  # noqa: E402
    PROMPT_VERSION,
    finding,
    target_parts,
    verify_search,
    verify_window,
)
from taxagent.paths import DATA  # noqa: E402

RELATION_DIR = DATA / "korpus_relasi"
MERGED_DIR = DATA / "korpus_gabung"


def _jsonl(f: Path) -> list[dict]:
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()] if f.exists() else []


def open_claims() -> tuple[list[dict], dict]:
    claims = [c for c in _jsonl(RELATION_DIR / "verifikasi.jsonl") if c.get("kelas") == "tanpa_bukti"]
    found = _jsonl(RELATION_DIR / "temuan_teks.jsonl") + _jsonl(RELATION_DIR / "temuan_llm.jsonl")
    pairs = {(t["dari"], t["ke"]) for t in found}
    left = [c for c in claims if (c["dari"], c["ke"]) not in pairs]
    return left, {"tanpa_bukti": len(claims), "sudah_ada_temuan_teks": len(claims) - len(left), "diperiksa": len(left)}


def reason_kind(reason: str) -> str:
    if reason.startswith(("target terverifikasi", "penerbit")):
        return reason.split(" ")[0] + " beda dari klaim"
    return reason.split(": ", 1)[1] if ": " in reason and not reason.startswith("LLM") else reason


def main() -> None:
    ap = argparse.ArgumentParser(description='Stage 4.6: LLM verification of JDIH claims without text evidence (``taxagent/corpus/claim_verify.py``).')
    ap.add_argument("--arm", dest="arm", choices=["window", "search"], required=True)
    ap.add_argument("--max", dest="max", type=int, default=0, help="hanya N klaim pertama (uji)")
    ap.add_argument("--parallel", dest="parallel", type=int, default=4)
    ap.add_argument("--adopt", action="store_true", help="salin hasil lengan ini ke temuan_llm_klaim.jsonl")
    ap.add_argument("--provider")
    ap.add_argument("--model")
    a = ap.parse_args()

    claims, counts0 = open_claims()
    if a.max:
        claims = claims[:a.max]
    index = _jsonl(MERGED_DIR / "indeks.jsonl")
    text_of = {e["kunci"]: e["teks"] for e in index if e.get("kunci") and e.get("teks")}
    client, model_id = llm_client(a.provider, a.model, RELATION_DIR / "cache_llm.jsonl")
    if client is None:
        sys.exit(3)
    run = verify_window if a.arm == "window" else verify_search

    def one(c: dict):
        f = text_of.get(c["dari"])
        if not f or not Path(f).exists():
            return c, None, "dokumen pengubah tanpa teks"
        own = target_parts(c["dari"])
        return c, run(c, Path(f).read_text(encoding="utf-8"), client, own), ""

    counts: collections.Counter = collections.Counter()
    reasons: collections.Counter = collections.Counter()
    results, steps = [], []
    with concurrent.futures.ThreadPoolExecutor(a.parallel) as ex:
        for n, fut in enumerate(concurrent.futures.as_completed([ex.submit(one, c) for c in claims]), 1):
            try:
                c, h, skip = fut.result()
            except Exception as exc:  # noqa: BLE001
                counts["galat"] += 1
                print(f"[{n}/{len(claims)}] GAGAL {type(exc).__name__}: {exc}", flush=True)
                continue
            if h is None:
                counts["tanpa_teks"] += 1
                continue
            counts["token"] += h.token
            steps.append(len(h.steps))
            if h.relation is None:
                counts["tetap_tanpa_bukti"] += 1
                reasons[reason_kind(h.reason)] += 1
            else:
                counts["terverifikasi"] += 1
                counts["jenis_beda_dari_klaim"] += h.relation.jenis != c["jenis"]
                results.append(finding(c, h.relation, a.arm, model_id))
            if n % 25 == 0 or n == len(claims):
                print(f"[{n}/{len(claims)}] {dict(counts)}", flush=True)
    suffix = "_uji" if a.max else ""
    out = RELATION_DIR / f"temuan_llm_klaim_{a.arm}{suffix}.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for t in results:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    sample = random.Random(20261019).sample(results, min(30, len(results)))
    with open(RELATION_DIR / f"sampel_klaim_llm_{a.arm}{suffix}.jsonl", "w", encoding="utf-8") as f:
        for t in sample:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    report = {"lengan": a.arm, **counts0, "dijalankan": len(claims), **counts,
              "per_jenis": dict(collections.Counter(t["jenis"] for t in results)),
              "alasan_tetap_tanpa_bukti": dict(reasons.most_common(15)),
              "langkah_rata": round(sum(steps) / len(steps), 2) if steps else 0,
              "model": model_id, "prompt": PROMPT_VERSION}
    (RELATION_DIR / f"laporan_klaim_llm_{a.arm}{suffix}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.adopt and not a.max:
        shutil.copyfile(out, RELATION_DIR / "temuan_llm_klaim.jsonl")
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
