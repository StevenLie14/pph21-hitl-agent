from __future__ import annotations

import re

from ..corpus.chunking import chunk, search_text
from ..corpus.full_graph import EDGE_TYPES, Plan, plan
from ..corpus.legal_basis import find_legal_basis
from ..corpus.relation_evidence import NormText

_NODE = ("judul", "stub", "punya_teks", "mulai", "berlaku_sampai", "label_pajak", "url", "url_berkas")


def from_texts(documents: dict[str, dict], relations: list[dict] = (), definitions: list[tuple[str, str, list[str]]] = ()
              ) -> MemoryClient:
    docs, chunks, basis = [], [], []
    for k, d in documents.items():
        text = d.get("teks") or ""
        docs.append({"kunci": k, "punya_teks": bool(text), **{x: v for x, v in d.items() if x != "teks"}})
        if text:
            basis += [{"dari": k, **x} for x in find_legal_basis(NormText.from_raw(text), k)]
        for p in chunk(text):
            chunks.append({"id": f"{k}#{p.order}", "peraturan": k, "urutan": p.order, "label_pasal": p.label,
                           "teks": p.text, "halaman": None, "teks_cari": search_text(k, d.get("judul") or "", p.label, p.text)})
    rels = {}
    for r in relations:
        x = {"bukti": "eksplisit", "sumber": "teks", "lewat": None, "kutipan": None, "pasal": None,
             "pasal_terdampak": [], "tgl_efektif": None, "tgl_perkiraan": None, **r}
        rels[(x["dari"], x["jenis"], x["ke"])] = x
    parameter = {nm: {} for _, nm, _ in definitions}
    return MemoryClient(plan(docs, rels, chunks, parameter, list(definitions), {}, basis=basis))


def _score(query: str, text: str) -> float:
    q = query.replace("\\", "")
    phrases = [f.lower() for f in q.split('"')[1::2] if f.strip()]
    words = [w.lower() for w in re.split(r'\s+|"', re.sub(r"\b(OR|AND)\b", " ", q)) if w.strip()]
    t = text.lower()
    return float(sum(t.count(f) * 3 for f in phrases) + sum(t.count(w) for w in words))


class MemoryClient:
    def __init__(self, r: Plan):
        self.r = r

    def _node_rows(self, k: str) -> dict:
        p = self.r.regulations[k]
        return {"kunci": k, **{x: p.get(x) for x in _NODE}}

    def _edge(self, x: dict, k: str, other: str) -> dict:
        return {"k": k, "lawan": other, "tipe": EDGE_TYPES[x["jenis"]], "bukti": x.get("bukti"), "sumber": x.get("sumber"),
                "tgl": x.get("tgl_efektif"), "tgl_perkiraan": x.get("tgl_perkiraan"), "lewat": x.get("lewat"),
                "pasal_terdampak": x.get("pasal_terdampak") or [], "pasal": x.get("pasal"), "kutipan": x.get("kutipan")}

    def query(self, cypher: str, **p) -> list[dict]:  # noqa: C901
        r = self.r
        if "queryNodes('chunk_search'" in cypher:
            k = p.get("k")
            result = []
            for c in r.chunks:
                if k and c["peraturan"] != k:
                    continue
                score = _score(p["q"], c["teks_cari"])
                if score:
                    reg = r.regulations[c["peraturan"]]
                    result.append({"id": c["id"], "label": c["label_pasal"], "teks": c["teks"], "halaman": c["halaman"],
                                  "score": score, "kunci": c["peraturan"],
                                  **{x: reg.get(x) for x in ("mulai", "berlaku_sampai", "label_pajak")}})
            return sorted(result, key=lambda x: -x["score"])[:p.get("n", 5)]
        if "-[e:BASED_ON]->(z:Regulation)" in cypher:
            return [{**{x: r.regulations[d["ke"]].get(x) for x in ("judul", "mulai", "berlaku_sampai", "label_pajak")},
                     "kunci": d["ke"], "bagian": d["bagian"], "peran": d["peran"], "pasal": d["pasal"]}
                    for d in sorted(r.basis, key=lambda d: d["urutan"]) if d["dari"] == p["k"]]
        if "-[e:BASED_ON]->(p:Regulation {key: $k})" in cypher:
            return [{**{x: r.regulations[d["dari"]].get(x) for x in ("judul", "mulai", "berlaku_sampai", "label_pajak",
                                                                    "tahun")},
                     "kunci": d["dari"], "bagian": d["bagian"], "pasal": d["pasal"]}
                    for d in r.basis if d["ke"] == p["k"] and d["peran"] != "perubahan"]
        if "DEFINES]->(:Parameter {name: $k})" in cypher:
            return [{**{x: r.regulations[d["peraturan"]].get(x) for x in ("mulai", "berlaku_sampai", "label_pajak")},
                     "kunci": d["peraturan"], "pasal": d["pasal"]} for d in r.defines if d["parameter"] == p["k"]]
        if "DEFINES" in cypher:
            return [{"nama": d["parameter"], "pasal": d["pasal"]} for d in r.defines if d["peraturan"] == p["k"]]
        if "(a:Regulation)-[e]->(p:Regulation {key: k})" in cypher:
            return [self._edge(x, k, x["dari"]) for k in p["ks"] for x in r.relations.values() if x["ke"] == k]
        if "(p:Regulation {key: k})-[e]->(z:Regulation)" in cypher:
            return [self._edge(x, k, x["ke"]) for k in p["ks"] for x in r.relations.values() if x["dari"] == k]
        if "article_label STARTS WITH 'Pasal '" in cypher:
            return [{"id": c["id"], "label": c["label_pasal"], "teks": c["teks"], "halaman": c["halaman"]}
                    for c in sorted(r.chunks, key=lambda c: c["urutan"])
                    if c["peraturan"] == p["k"] and c["label_pasal"].startswith("Pasal ")]
        if "UNWIND $ks AS k MATCH (p:Regulation {key: k}) RETURN" in cypher:
            return [self._node_rows(k) for k in p["ks"] if k in r.regulations]
        if "toLower(p.title) CONTAINS $q" in cypher:
            return [self._node_rows(k) for k, x in r.regulations.items() if p["q"] in (x.get("judul") or "").lower()][:5]
        if "MATCH (p:Regulation {key: $k}) RETURN" in cypher:
            return [self._node_rows(p["k"])] if p["k"] in r.regulations else []
        raise NotImplementedError(f"template query tidak dikenal: {cypher[:80]}")

    def run(self, cypher: str, **p) -> None:
        raise NotImplementedError("MemoryClient hanya-baca")
