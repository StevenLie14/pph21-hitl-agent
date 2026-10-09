from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from taxagent.corpus.faq import collect, graph_plan, write_graph, write_locations  # noqa: E402
from taxagent.paths import DATA  # noqa: E402

FAQ_DIR = DATA / "faq"


def cmd_collect(_a) -> None:
    from taxagent.monitor.sources import fetch

    print(json.dumps(collect(FAQ_DIR, fetch), ensure_ascii=False))


def cmd_graph(a) -> None:
    nodes, references, summary = graph_plan(FAQ_DIR)
    print(json.dumps(summary, ensure_ascii=False))
    if a.dry_run:
        for n in nodes[:5]:
            print(f"- {n['id']}: {n['pertanyaan'][:90]}")
        return
    from taxagent.environment import load_neo4j_env
    from taxagent.monitor.graph_v2 import Neo4jV2Client

    load_neo4j_env()
    client = Neo4jV2Client()
    try:
        if a.locations_only:
            print(json.dumps({"faq_diperbarui": write_locations(client, nodes)}))
            return
        print(json.dumps(write_graph(client, nodes, references), ensure_ascii=False))
    finally:
        client.close()


def main() -> None:
    ap = argparse.ArgumentParser(description='DJP FAQ into the ``neo4j-v2`` graph as supporting information (see ``taxagent/corpus/faq.py``). From the repo root:')
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("collect").set_defaults(func=cmd_collect)
    g = sub.add_parser("graph")
    g.add_argument("--dry-run", dest="dry_run", action="store_true")
    g.add_argument("--locations-only", dest="locations_only", action="store_true",
                   help="hanya tambahkan lampiran PDF + halaman ke FAQ yang ada (vektor tidak tersentuh)")
    g.set_defaults(func=cmd_graph)
    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
