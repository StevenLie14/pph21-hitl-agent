from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from taxagent.corpus.legal_basis import find_legal_basis  # noqa: E402
from taxagent.corpus.relation_evidence import NormText  # noqa: E402
from taxagent.monitor.identity import canon_id  # noqa: E402
from taxagent.paths import DATA  # noqa: E402

MERGED_DIR = DATA / "korpus_gabung"
RELATION_DIR = DATA / "korpus_relasi"
BATCH = 1000


def main() -> None:
    ap = argparse.ArgumentParser(description='Legal-basis relations (Menimbang/Mengingat) of the whole corpus (``taxagent.corpus.legal_basis``).')
    ap.add_argument("--write", dest="write", action="store_true", help="MERGE edge BASED_ON ke neo4j-v2")
    a = ap.parse_args()

    chosen: dict[str, dict] = {}
    for b in (MERGED_DIR / "indeks.jsonl").read_text(encoding="utf-8").splitlines():
        x = json.loads(b)
        if not x.get("kunci") or not x.get("teks") or not Path(x["teks"]).exists():
            continue
        if x["kunci"] not in chosen or (x["sumber"] == "jdih" and chosen[x["kunci"]]["sumber"] != "jdih"):
            chosen[x["kunci"]] = x
    result, counts = [], Counter()
    for i, (k, x) in enumerate(sorted(chosen.items()), 1):
        r = find_legal_basis(NormText.from_raw(Path(x["teks"]).read_text(encoding="utf-8")), k)
        counts["dok_dengan_dasar" if r else "dok_tanpa_dasar"] += 1
        for y in r:
            counts[f"{y['bagian']}:{y['peran']}"] += 1
            result.append({"dari": k, **y, "dok_sumber": x["sumber"]})
        if i % 2000 == 0:
            print(f"{i}/{len(chosen)}", flush=True)
    with open(RELATION_DIR / "dasar_hukum.jsonl", "w", encoding="utf-8") as f:
        for y in result:
            f.write(json.dumps(y, ensure_ascii=False) + "\n")
    counts["edge"] = len(result)
    counts["target_unik"] = len({y["ke"] for y in result})
    counts["target_teratas"] = Counter(y["ke"] for y in result if y["peran"] != "perubahan").most_common(15)
    (RELATION_DIR / "laporan_dasar.json").write_text(json.dumps(counts, ensure_ascii=False, indent=1),
                                                     encoding="utf-8")
    print(json.dumps(counts, ensure_ascii=False, indent=1))
    if not a.write:
        return

    from taxagent.environment import load_neo4j_env
    from taxagent.graph_names import graph_props
    from taxagent.monitor.graph_v2 import Neo4jV2Client

    load_neo4j_env()
    neo = Neo4jV2Client()
    try:
        existing = {r["k"] for r in neo.query("MATCH (p:Regulation) RETURN p.key AS k")}
        stubs = []
        for t in sorted({y["ke"] for y in result} - existing):
            i = canon_id(t)
            stubs.append({"kunci": t, "stub": True, "jenis": i.kind if i else None, "nomor": i.number if i else None,
                          "tahun": i.year if i else None})
        for j in range(0, len(stubs), BATCH):
            neo.run("UNWIND $baris AS b MERGE (p:Regulation {key: b.key}) ON CREATE SET p += b",
                    baris=[graph_props({x: v for x, v in s.items() if v is not None}) for s in stubs[j:j + BATCH]])
        rows = [{"dari": y["dari"], "ke": y["ke"],
                 "p": graph_props({x: v for x, v in y.items() if x not in ("dari", "ke") and v is not None})}
                for y in result if y["dari"] in existing]
        for j in range(0, len(rows), BATCH):
            neo.run("UNWIND $baris AS b MATCH (a:Regulation {key: b.dari}), (z:Regulation {key: b.ke}) "
                    "MERGE (a)-[e:BASED_ON {section: b.p.section}]->(z) SET e += b.p", baris=rows[j:j + BATCH])
            print(f"  BASED_ON {min(j + BATCH, len(rows))}/{len(rows)}", flush=True)
        print(f"ditulis: {len(rows)} edge, {len(stubs)} stub baru")
    finally:
        neo.close()


if __name__ == "__main__":
    main()
