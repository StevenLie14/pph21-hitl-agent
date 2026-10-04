from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field

from ..graph_names import graph_props
from ..settings import get_settings

CHUNK_SIZE, OVERLAP = 1500, 200
EDGE_TYPES = {"mencabut": "MENCABUT", "mencabut_sebagian": "MENCABUT_SEBAGIAN", "mengubah": "MENGUBAH"}


def node_key(kind: str, number: int, year: int) -> str:
    return f"{kind}|{number}|{year}"


def node_name(kind: str, number: int, year: int) -> str:
    if kind in ("UU", "PERPPU", "PP", "PMK", "PERPRES"):
        return f"{kind} {number} Tahun {year}"
    return f"{kind} {number}/{year}"


def chunk(text: str, size: int = CHUNK_SIZE, overlap: int = OVERLAP) -> list[str]:
    t = " ".join((text or "").split())
    if not t:
        return []
    result, i = [], 0
    while i < len(t):
        result.append(t[i:i + size])
        if i + size >= len(t):
            break
        i += size - overlap
    return result


@dataclass
class Plan:
    regulations: dict[str, dict] = field(default_factory=dict)
    relations: list[dict] = field(default_factory=list)
    chunks: list[dict] = field(default_factory=list)
    parameters: dict[str, dict] = field(default_factory=dict)
    defines: list[dict] = field(default_factory=list)


def plan(documents: dict[str, dict], relations_by_doc: dict[str, list], portal_by_doc: dict[str, set],
            parameter: dict[str, dict], definitions: list[tuple[str, str, list[str]]], meta: dict) -> Plan:
    r = Plan()
    for k, d in documents.items():
        props = {x: v for x, v in d.items() if x != "teks"}
        r.regulations[k] = {**props, "kunci": k, "ringkas": False}
        for n, piece in enumerate(chunk(d.get("teks", ""))):
            r.chunks.append({"id": f"{k}#{n}", "peraturan": k, "urutan": n, "teks": piece})
    for k, rels in relations_by_doc.items():
        for rel in rels:
            target = node_key(rel.jenis_peraturan, rel.nomor, rel.tahun)
            if target not in r.regulations:
                r.regulations[target] = {"kunci": target, "nama": node_name(rel.jenis_peraturan, rel.nomor, rel.tahun),
                                   "jenis": rel.jenis_peraturan, "nomor": rel.nomor, "tahun": rel.tahun, "ringkas": True}
            r.relations.append({"dari": k, "ke": target, "tipe": EDGE_TYPES[rel.jenis], "properti": {
                "kutipan": rel.kutipan, "pasal": list(rel.pasal), "sumber": "llm_terverifikasi",
                "model": meta.get("model"), "prompt_versi": meta.get("prompt"), "dibangun": meta.get("tanggal"),
                "portal_setuju": rel.kunci in portal_by_doc.get(k, set()),
            }})
    for name, p in parameter.items():
        r.parameters[name] = {"nama": name, "deskripsi": p.get("deskripsi", ""), "istilah": list(p.get("istilah", []))}
    for reg_key, name, articles in definitions:
        if reg_key in r.regulations and name in r.parameters:
            r.defines.append({"peraturan": reg_key, "parameter": name, "pasal": articles})
    return r


SCHEMA_CYPHER = [
    "CREATE CONSTRAINT regulation_key IF NOT EXISTS FOR (p:Regulation) REQUIRE p.key IS UNIQUE",
    "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT parameter_name IF NOT EXISTS FOR (k:Parameter) REQUIRE k.name IS UNIQUE",
    "CREATE FULLTEXT INDEX chunk_text IF NOT EXISTS FOR (c:Chunk) ON EACH [c.text]",
]


def write(client, r: Plan) -> dict:
    for c in SCHEMA_CYPHER:
        client.run(c)
    client.run("UNWIND $baris AS b MERGE (p:Regulation {key: b.key}) SET p += b",
               baris=[graph_props(p) for p in r.regulations.values()])
    client.run("UNWIND $baris AS b MATCH (p:Regulation {key: b.peraturan}) MERGE (c:Chunk {id: b.id}) "
              "SET c.text = b.teks, c.order = b.urutan MERGE (c)-[:PART_OF]->(p)", baris=r.chunks)
    for edge_type in EDGE_TYPES.values():
        rows = [{**x, "properti": graph_props(x["properti"])} for x in r.relations if x["tipe"] == edge_type]
        client.run(f"UNWIND $baris AS b MATCH (a:Regulation {{key: b.dari}}), (z:Regulation {{key: b.ke}}) "
                  f"MERGE (a)-[e:{edge_type}]->(z) SET e += b.properti", baris=rows)
    client.run("UNWIND $baris AS b MERGE (k:Parameter {name: b.name}) SET k += b",
               baris=[graph_props(x) for x in r.parameters.values()])
    client.run("UNWIND $baris AS b MATCH (p:Regulation {key: b.peraturan}), (k:Parameter {name: b.parameter}) "
              "MERGE (p)-[e:DEFINES]->(k) SET e.article = b.pasal", baris=r.defines)
    return {"peraturan": len(r.regulations), "relasi": len(r.relations), "potongan": len(r.chunks),
            "parameter": len(r.parameters), "mendefinisikan": len(r.defines)}


class Neo4jV2Client:
    def __init__(self) -> None:
        from neo4j import GraphDatabase

        cfg = get_settings()
        uri, password = cfg.neo4j_v2_uri, cfg.neo4j_v2_password
        if not uri or not password:
            raise RuntimeError("NEO4J_V2_URI dan NEO4J_V2_PASSWORD wajib diset (.env aplikasi utama)")
        self._driver = GraphDatabase.driver(uri, auth=(cfg.neo4j_v2_user, password))
        self._driver.verify_connectivity()

    def query(self, cypher: str, **params) -> list[dict]:
        with self._driver.session() as s:
            return [dict(x) for x in s.run(cypher, **params)]

    def run(self, cypher: str, **params) -> None:
        with self._driver.session() as s:
            s.run(cypher, **params).consume()

    def close(self) -> None:
        self._driver.close()


def today() -> str:
    return _dt.date.today().isoformat()
