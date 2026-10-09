from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from taxagent.corpus.relation_claims import collect  # noqa: E402
from taxagent.paths import DATA  # noqa: E402

JDIH_DIR = DATA / "korpus_jdih"
MERGED_DIR = DATA / "korpus_gabung"
RELATION_DIR = DATA / "korpus_relasi"


def main() -> None:
    ap = argparse.ArgumentParser(description='Stage 4.1: inter-regulation relation claims from the JDIH document pages (``taxagent.corpus.relation_claims``).')
    ap.add_argument("--jdih", type=Path, default=JDIH_DIR)
    ap.add_argument("--merged", dest="merged", type=Path, default=MERGED_DIR)
    ap.add_argument("--out", dest="out", type=Path, default=RELATION_DIR)
    a = ap.parse_args()

    doc_keys = {}
    for line in (a.merged / "indeks.jsonl").read_text(encoding="utf-8").splitlines():
        x = json.loads(line)
        if x["sumber"] == "jdih" and x.get("kunci"):
            doc_keys[x["id"]] = x["kunci"]
    pages = [(f.stem, json.loads(f.read_text(encoding="utf-8"))) for f in sorted((a.jdih / "halaman").glob("*.json"))]
    claims, report = collect(pages, doc_keys)

    a.out.mkdir(parents=True, exist_ok=True)
    with open(a.out / "klaim.jsonl", "w", encoding="utf-8") as f:
        for k in claims:
            f.write(json.dumps(k.to_dict(), ensure_ascii=False) + "\n")
    (a.out / "laporan_klaim.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {k: v for k, v in report.items() if not k.startswith("contoh") and k != "diri_sendiri"}
    print(json.dumps(summary, ensure_ascii=False))
    print(f"diri sendiri: {report['diri_sendiri']}")
    print(f"-> {a.out / 'klaim.jsonl'}")


if __name__ == "__main__":
    main()
