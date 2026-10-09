from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field

from ..graph_names import graph_props
from ..monitor.identity import canon_id
from .status import Edge, compute, interval

EDGE_TYPES = {"mencabut": "MENCABUT", "mencabut_sebagian": "MENCABUT_SEBAGIAN", "mengubah": "MENGUBAH",
              "ditetapkan_menjadi": "DITETAPKAN_MENJADI", "memperpanjang": "MEMPERPANJANG",
              "mengatur_lebih_lanjut": "MENGATUR_LEBIH_LANJUT"}
_EVIDENCE_RANK = {"eksplisit": 0, "tersirat": 1, "tanpa_bukti": 2, "belum_dicek": 3}
BATCH = 1000


@dataclass
class Plan:
    regulations: dict[str, dict] = field(default_factory=dict)
    relations: dict[tuple[str, str, str], dict] = field(default_factory=dict)
    chunks: list[dict] = field(default_factory=list)
    parameters: dict[str, dict] = field(default_factory=dict)
    defines: list[dict] = field(default_factory=list)
    build: dict = field(default_factory=dict)
    basis: list[dict] = field(default_factory=list)


def _evidence(label: str) -> str:
    return "belum_dicek" if label == "belum_bisa_dicek" else label


def merge_relations(verifications: list[dict], findings: list[dict], doc_dates: dict[str, str | None]) -> dict:
    rels: dict[tuple[str, str, str], dict] = {}
    for v in verifications:
        k = (v["dari"], v["jenis"], v["ke"])
        rels[k] = {"dari": k[0], "jenis": k[1], "ke": k[2], "bukti": _evidence(v["kelas"]), "sumber": "jdih",
                   "lewat": v.get("lewat"), "kutipan": v.get("kutipan"), "pasal": v.get("pasal"),
                   "bagian": v.get("bagian"), "pasal_terdampak": v.get("pasal_terdampak") or [],
                   "dicatat_di": v.get("dicatat_di", []), "tgl_efektif": v.get("tgl_efektif"),
                   "tgl_efektif_sumber": v.get("tgl_efektif_sumber"), "tgl_jdih": v.get("tgl_mulai_berlaku") or [],
                   "sumber_teks": v.get("sumber_teks"), "mutu_teks": v.get("mutu_teks")}
    for t in findings:
        k = (t["dari"], t["jenis"], t["ke"])
        new = {"dari": k[0], "jenis": k[1], "ke": k[2], "bukti": t["kelas"], "sumber": t.get("sumber") or "teks",
               "lewat": t.get("lewat"),
               "kutipan": t.get("kutipan"), "pasal": t.get("pasal"), "bagian": t.get("bagian"),
               "pasal_terdampak": t.get("pasal_terdampak") or [], "dicatat_di": [],
               "tgl_efektif": t.get("tgl_efektif"), "tgl_efektif_sumber": t.get("tgl_efektif_sumber"), "tgl_jdih": []}
        old = rels.get(k)
        if old is None:
            rels[k] = new
            continue
        old["sumber"] = "jdih+teks" if old["sumber"] == "jdih" else old["sumber"]
        if _EVIDENCE_RANK[new["bukti"]] < _EVIDENCE_RANK[old["bukti"]]:
            for f in ("bukti", "lewat", "kutipan", "pasal", "bagian", "pasal_terdampak"):
                old[f] = new[f]
            old["tgl_efektif"] = old["tgl_efektif"] or new["tgl_efektif"]
        elif new["pasal_terdampak"] and not old["pasal_terdampak"] and new["bukti"] == old["bukti"]:
            old["pasal_terdampak"] = new["pasal_terdampak"]
    for r in rels.values():
        if r["tgl_efektif_sumber"] == "tidak_terekstrak" or not r["tgl_efektif"]:
            r["tgl_efektif"] = None
            r["tgl_perkiraan"] = doc_dates.get(r["dari"])
        else:
            r["tgl_perkiraan"] = None
    return rels


def edge_from(r: dict) -> Edge:
    return Edge(r["dari"], r["jenis"], r["ke"], r["bukti"], r["tgl_efektif"], r.get("tgl_perkiraan"), r.get("lewat"),
                list(r.get("pasal_terdampak") or []))


def plan(documents: list[dict], relations: dict, chunks: list[dict], parameter: dict[str, dict],
         definitions: list[tuple[str, str, list[str]]], meta: dict, day: dt.date | None = None,
         basis: list[dict] | None = None) -> Plan:
    day = day or dt.date.today()
    r = Plan(relations=relations, chunks=chunks, build=meta, basis=list(basis or []))
    for d in documents:
        r.regulations[d["kunci"]] = {**d, "stub": False}
    for x in r.basis:
        if x["ke"] not in r.regulations and x["ke"] not in {y for v in relations.values() for y in (v["dari"], v["ke"])}:
            ident = canon_id(x["ke"])
            r.regulations[x["ke"]] = {"kunci": x["ke"], "stub": True, "jenis": ident.kind if ident else None,
                                    "nomor": ident.number if ident else None, "tahun": ident.year if ident else None}
    for x in relations.values():
        for k in (x["dari"], x["ke"]):
            if k not in r.regulations:
                ident = canon_id(k)
                r.regulations[k] = {"kunci": k, "stub": True, "jenis": ident.kind if ident else None,
                                  "nomor": ident.number if ident else None, "tahun": ident.year if ident else None}
    incoming, outgoing = defaultdict(list), defaultdict(list)
    for x in relations.values():
        e = edge_from(x)
        incoming[x["ke"]].append(e)
        outgoing[x["dari"]].append(e)
    for k, p in r.regulations.items():
        st = compute(k, day, incoming[k], outgoing[k], start=p.get("mulai"), valid_until=p.get("berlaku_sampai"),
                     pajak_label=p.get("label_pajak"))
        p.update({"status_hari_ini": st.status, "status_sejak": st.since, "status_pasti": st.certain,
                  "status_dihitung": day.isoformat(),
                  **interval(k, incoming[k], outgoing[k], start=p.get("mulai"), valid_until=p.get("berlaku_sampai"))})
    for name, param in parameter.items():
        r.parameters[name] = {"nama": name, "deskripsi": param.get("deskripsi", ""), "istilah": list(param.get("istilah", []))}
    for reg_key, name, articles in definitions:
        if reg_key in r.regulations and name in r.parameters:
            r.defines.append({"peraturan": reg_key, "parameter": name, "pasal": articles})
    return r


SCHEMA = [
    "CREATE CONSTRAINT regulation_key IF NOT EXISTS FOR (p:Regulation) REQUIRE p.key IS UNIQUE",
    "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT parameter_name IF NOT EXISTS FOR (k:Parameter) REQUIRE k.name IS UNIQUE",
    "CREATE INDEX regulation_kind_year IF NOT EXISTS FOR (p:Regulation) ON (p.kind, p.year)",
    "CREATE FULLTEXT INDEX chunk_search IF NOT EXISTS FOR (c:Chunk) ON EACH [c.search_text]",
]


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None and not isinstance(v, dict)}


def clear(client) -> None:
    client.run("MATCH (n) CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 2000 ROWS")
    for x in client.query("SHOW CONSTRAINTS YIELD name RETURN name"):
        client.run(f"DROP CONSTRAINT `{x['name']}` IF EXISTS")
    for x in client.query("SHOW INDEXES YIELD name, type WHERE type <> 'LOOKUP' RETURN name"):
        client.run(f"DROP INDEX `{x['name']}` IF EXISTS")


def update(client, r: Plan, report=print) -> dict:
    managed = {k for p in r.regulations.values() for k in graph_props(_clean(p))}
    current = {x["key"]: set(x["props"]) for x in client.query(
        "MATCH (p:Regulation) WHERE p.key IN $keys RETURN p.key AS key, keys(p) AS props", keys=list(r.regulations))}
    rows, stale = [], 0
    for key, p in r.regulations.items():
        props = graph_props(_clean(p))
        drop = sorted((current.get(key, set()) & managed) - set(props))
        stale += bool(drop)
        rows.append({"key": key, "p": props, "drop": drop})
    for i in range(0, len(rows), BATCH):
        client.run("UNWIND $baris AS b MERGE (p:Regulation {key: b.key}) SET p += b.p "
                   "WITH p, b CALL (p, b) { UNWIND b.drop AS k WITH p, k SET p[k] = null }", baris=rows[i:i + BATCH])
        report(f"  peraturan {min(i + BATCH, len(rows))}/{len(rows)}")
    planned = set()
    for kind, edge_type in EDGE_TYPES.items():
        edges = [{"dari": x["dari"], "ke": x["ke"],
                  "p": graph_props(_clean({k: v for k, v in x.items() if k not in ("dari", "ke")}))}
                 for x in r.relations.values() if x["jenis"] == kind]
        planned |= {(edge_type, e["dari"], e["ke"]) for e in edges}
        for i in range(0, len(edges), BATCH):
            client.run(f"UNWIND $baris AS b MATCH (a:Regulation {{key: b.dari}}), (z:Regulation {{key: b.ke}}) "
                       f"MERGE (a)-[e:{edge_type}]->(z) SET e += b.p", baris=edges[i:i + BATCH])
        report(f"  {edge_type} {len(edges)}")
    in_graph = client.query("MATCH (a:Regulation)-[e]->(z:Regulation) WHERE type(e) IN $types "
                            "RETURN type(e) AS t, a.key AS dari, z.key AS ke", types=list(EDGE_TYPES.values()))
    counts = {"peraturan": len(r.regulations), "properti_dihapus_pada": stale, "relasi": len(r.relations),
              "relasi_graf_di_luar_rencana": sum((x["t"], x["dari"], x["ke"]) not in planned for x in in_graph)}
    client.run("CREATE (b:Build) SET b = $p",
               p=graph_props(_clean({**r.build, "mode": "update", **{f"jumlah_{k}": v for k, v in counts.items()}})))
    return counts


def write(client, r: Plan, report=print) -> dict:
    for c in SCHEMA:
        client.run(c)

    def per_batch(cypher: str, rows: list[dict], label: str) -> None:
        for i in range(0, len(rows), BATCH):
            client.run(cypher, baris=rows[i:i + BATCH])
            report(f"  {label} {min(i + BATCH, len(rows))}/{len(rows)}")

    per_batch("UNWIND $baris AS b MERGE (p:Regulation {key: b.key}) SET p += b",
              [graph_props(_clean(p)) for p in r.regulations.values()], "peraturan")
    for kind, edge_type in EDGE_TYPES.items():
        rows = [{"dari": x["dari"], "ke": x["ke"],
                 "p": graph_props(_clean({k: v for k, v in x.items() if k not in ("dari", "ke")}))}
                for x in r.relations.values() if x["jenis"] == kind]
        per_batch(f"UNWIND $baris AS b MATCH (a:Regulation {{key: b.dari}}), (z:Regulation {{key: b.ke}}) "
                  f"MERGE (a)-[e:{edge_type}]->(z) SET e += b.p", rows, edge_type)
    per_batch("UNWIND $baris AS b MATCH (a:Regulation {key: b.dari}), (z:Regulation {key: b.ke}) "
              "MERGE (a)-[e:BASED_ON {section: b.p.section}]->(z) SET e += b.p",
              [{"dari": x["dari"], "ke": x["ke"], "p": graph_props(_clean({k: v for k, v in x.items() if k not in ("dari", "ke")}))}
               for x in r.basis if x["dari"] in r.regulations], "BASED_ON")
    per_batch("UNWIND $baris AS b MATCH (p:Regulation {key: b.peraturan}) MERGE (c:Chunk {id: b.id}) "
              "SET c += b.p MERGE (c)-[:PART_OF]->(p)",
              [{"id": c["id"], "peraturan": c["peraturan"], "p": graph_props(_clean(c))} for c in r.chunks], "potongan")
    client.run("UNWIND $baris AS b MERGE (k:Parameter {name: b.name}) SET k += b",
               baris=[graph_props(x) for x in r.parameters.values()])
    client.run("UNWIND $baris AS b MATCH (p:Regulation {key: b.peraturan}), (k:Parameter {name: b.parameter}) "
               "MERGE (p)-[e:DEFINES]->(k) SET e.article = b.pasal", baris=r.defines)
    counts = {"peraturan": len(r.regulations), "stub": sum(p["stub"] for p in r.regulations.values()),
              "relasi": len(r.relations), "potongan": len(r.chunks), "parameter": len(r.parameters),
              "mendefinisikan": len(r.defines), "berdasarkan": len(r.basis)}
    client.run("CREATE (b:Build) SET b = $p",
               p=graph_props(_clean({**r.build, **{f"jumlah_{k}": v for k, v in counts.items()}})))
    return counts
