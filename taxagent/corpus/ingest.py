from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass, field

from ..graph_names import graph_props
from ..monitor.identity import canon_id
from .chunking import chunk, search_text
from .full_graph import _EVIDENCE_RANK, EDGE_TYPES, merge_relations
from .legal_basis import find_legal_basis
from .quality import QualityInput, Vocabulary, assess
from .relation_claims import collect
from .relation_evidence import NormText, effective_date, evidence
from .relation_text import find_relations
from .status import Edge, compute, interval

RE_TAX = re.compile(r"pajak|perpajakan|\bpph\b|\bppn\b|penghasilan|bea meterai|fiskal|ditanggung pemerintah", re.I)
_QUALITY_SOURCE = {"lapisan_pdf": "jdih_digital", "htm_jdih": "jdih_htm", "ocr": "jdih_ocr", "ocr_cache": "jdih_ocr",
                   "pajak.go.id": "pajak",
                   "lampiran_pdf": "jdih_digital", "lampiran_ocr": "jdih_ocr"}
_RE_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_ALL_TYPES = "[" + ",".join(f"'{t}'" for t in EDGE_TYPES.values()) + "]"


@dataclass
class Document:
    key: str
    source: str
    id: str
    number: str = ""
    title: str = ""
    kind: str = ""
    text: str | None = None
    text_source: str | None = None
    pages: dict | None = None
    detail: dict | None = None
    file_url: str | None = None
    file_kind: str | None = None
    pdf_pages: int | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class Package:
    nodes: dict
    relations: dict[tuple[str, str, str], dict]
    chunks: list[dict]
    llm_remaining: list[dict] = field(default_factory=list)
    basis: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {"kunci": self.nodes["kunci"], "sumber": self.nodes["sumber_dok"], "punya_teks": self.nodes["punya_teks"],
                "mutu": self.nodes.get("mutu"), "mulai": self.nodes.get("mulai"),
                "relasi": [f"{r['dari']} -{r['jenis']}-> {r['ke']} ({r['bukti']})" for r in self.relations.values()],
                "potongan": len(self.chunks), "sisa_llm": len(self.llm_remaining),
                "dasar_hukum": [f"{x['bagian']}:{x['ke']}" for x in self.basis], "catatan": self.notes}


def package(d: Document, parents: dict[str, set[str]] | None = None, vocabulary: Vocabulary | None = None,
            split=None) -> Package:
    ident = canon_id(d.key)
    page, detail = d.pages or {}, d.detail or {}
    notes = list(d.notes)
    node = {"kunci": d.key, "jenis_dok": d.kind, "nomor_asli": d.number, "judul": d.title or page.get("judul"),
            "tahun": ident.year if ident else None, "sumber_dok": d.source, "punya_teks": bool(d.text),
            "url_berkas": d.file_url, "jenis_berkas": d.file_kind, "sumber_teks": d.text_source}
    if d.source == "jdih":
        node["id_jdih" if _RE_UUID.match(d.id) else "slug_jdih"] = d.id
        node.update({"url": page.get("url"), "tgl_penetapan": page.get("tgl_penetapan"),
                     "tgl_pengundangan": page.get("tgl_pengundangan"), "tgl_mulai_jdih": page.get("tgl_mulai_berlaku"),
                     "tgl_selesai_jdih": page.get("tgl_selesai_berlaku"), "riwayat_jdih": page.get("riwayat_terakhir")})
    else:
        node.update({"slug_pajak": d.id, "url": detail.get("url"), "tgl_penetapan": detail.get("tanggal") or None,
                     "label_pajak": detail.get("status") or None})

    if d.text and vocabulary is not None:
        h = assess(QualityInput(d.key, _QUALITY_SOURCE.get(d.text_source or "", "pajak"), d.text,
                                ident.number if ident else None, ident.year if ident else None, d.pdf_pages), vocabulary)
        node["mutu"] = h.status
        if h.status != "andal":
            notes.append(f"mutu teks {h.status}: {'; '.join(h.alasan)[:200]}")

    t = NormText.from_raw(d.text) if d.text else None
    eff_date, eff_source = (effective_date(t, node.get("tgl_pengundangan"), node.get("tgl_penetapan")) if t
                            else (None, "tidak_terekstrak"))
    if eff_date:
        node["mulai"], node["mulai_sumber"] = eff_date, f"teks:{eff_source}"
    elif node.get("tgl_mulai_jdih"):
        node["mulai"], node["mulai_sumber"] = node["tgl_mulai_jdih"], "jdih"
    elif node.get("tgl_pengundangan") or node.get("tgl_penetapan"):
        node["mulai"] = node.get("tgl_pengundangan") or node.get("tgl_penetapan")
        node["mulai_sumber"] = "perkiraan:pengundangan_atau_penetapan"

    verified = []
    if d.pages:
        claims, _ = collect([(d.id, d.pages)], {d.id: d.key})
        for k in claims:
            kd = k.to_dict()
            if kd["dari"] != d.key:
                verified.append({**kd, "kelas": "belum_bisa_dicek", "catatan": "pengubah lain: dicek saat bangun ulang",
                                 "tgl_efektif": None, "tgl_efektif_sumber": "tidak_terekstrak"})
            elif t is None:
                verified.append({**kd, "kelas": "belum_bisa_dicek", "catatan": "teks_belum_ada",
                                 "tgl_efektif": None, "tgl_efektif_sumber": "tidak_terekstrak"})
            else:
                verified.append({**kd, **evidence(t, kd["ke"], kd["jenis"], parents), "sumber_teks": d.text_source,
                                 "mutu_teks": node.get("mutu"), "tgl_efektif": eff_date, "tgl_efektif_sumber": eff_source})
    found, leftover = [], []
    if t is not None:
        rels, leftover = find_relations(t, d.key, d.kind)
        for r in rels:
            src, dst = (r["ke"], d.key) if r.pop("arah", None) == "masuk" else (d.key, r["ke"])
            found.append({"dari": src, "jenis": r.pop("jenis"), "ke": dst,
                          **{k: v for k, v in r.items() if k != "ke"}, "tgl_efektif": eff_date, "tgl_efektif_sumber": eff_source})
    relations = merge_relations(verified, found, {d.key: node.get("tgl_pengundangan") or node.get("tgl_penetapan")})

    chunks = []
    if d.text and (d.source == "pajak" or RE_TAX.search(node.get("judul") or "")):
        for p in chunk(d.text):
            chunks.append({"id": f"{d.key}#{p.order}", "peraturan": d.key, "urutan": p.order, "label_pasal": p.label,
                           "teks": p.text, "offset_awal": p.start, "offset_akhir": p.end, "halaman": None,
                           "teks_cari": search_text(d.key, node.get("judul") or "", p.label, p.text, split)})
    if not d.text:
        notes.append("tanpa teks: relasi hanya dari klaim JDIH (belum dicek); masukkan ulang setelah teks ada")
    basis = [{"dari": d.key, **x} for x in find_legal_basis(t, d.key)] if t is not None else []
    return Package(node, relations, chunks, llm_remaining=leftover, notes=notes, basis=basis)


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None and not isinstance(v, dict)}


def _edges(client, keys: list[str]) -> tuple[dict[str, list[Edge]], dict[str, list[Edge]]]:
    rows = client.query(f"UNWIND $ks AS k MATCH (a:Regulation)-[e]->(z:Regulation) WHERE (a.key = k OR z.key = k) "
                        f"AND type(e) IN {_ALL_TYPES} RETURN DISTINCT k, a.key AS dari, toLower(type(e)) AS jenis, "
                        "z.key AS ke, e.evidence AS bukti, e.effective_date AS tgl, e.estimated_date AS tgl_perkiraan, "
                        "e.via AS lewat, e.affected_articles AS pasal_terdampak", ks=keys)
    incoming, outgoing = {k: [] for k in keys}, {k: [] for k in keys}
    for b in rows:
        e = Edge(b["dari"], b["jenis"], b["ke"], b["bukti"] or "belum_dicek", b["tgl"], b["tgl_perkiraan"], b["lewat"],
                 list(b["pasal_terdampak"] or []))
        (incoming if b["ke"] == b["k"] else outgoing)[b["k"]].append(e)
    return incoming, outgoing


def recompute_status(client, keys: list[str], day: dt.date) -> int:
    nodes = client.query("UNWIND $ks AS k MATCH (p:Regulation {key: k}) RETURN p.key AS kunci, p.start AS mulai, "
                         "p.valid_until AS berlaku_sampai, p.pajak_label AS label_pajak", ks=keys)
    incoming, outgoing = _edges(client, [n["kunci"] for n in nodes])
    rows = []
    for n in nodes:
        k = n["kunci"]
        st = compute(k, day, incoming[k], outgoing[k], start=n["mulai"], valid_until=n["berlaku_sampai"],
                     pajak_label=n["label_pajak"])
        rows.append({"kunci": k, "p": graph_props(_clean({
            "status_hari_ini": st.status, "status_sejak": st.since, "status_pasti": st.certain,
            "status_dihitung": day.isoformat(),
            **interval(k, incoming[k], outgoing[k], start=n["mulai"], valid_until=n["berlaku_sampai"])}))})
    client.run("UNWIND $baris AS b MATCH (p:Regulation {key: b.kunci}) "
               "REMOVE p.in_force_from, p.in_force_until SET p += b.p", baris=rows)
    return len(rows)


def parents_from_graph(client, keys: list[str]) -> dict[str, set[str]]:
    if not keys:
        return {}
    return {b["k"]: set(b["ys"]) for b in client.query(
        "UNWIND $ks AS k MATCH (:Regulation {key: k})-[:MENGUBAH*1..3]->(y:Regulation) "
        "RETURN k, collect(DISTINCT y.key) AS ys", ks=keys)}


def claim_targets(d: Document) -> list[str]:
    return sorted({r["identitas"] for r in (d.pages or {}).get("relasi", []) if r.get("identitas")})


def write(client, p: Package, meta: dict, day: dt.date | None = None) -> dict:
    day = day or dt.date.today()
    k = p.nodes["kunci"]
    existing = client.query("MATCH (p:Regulation {key: $k}) RETURN p.stub AS stub, p.doc_source AS sumber, "
                            "p.has_text AS punya_teks", k=k)
    if p.nodes["sumber_dok"] == "pajak" and existing and existing[0]["sumber"] == "jdih" and existing[0]["punya_teks"]:
        return {"kunci": k, "dilewati": "sudah ada dari JDIH berteks (JDIH sumber utama)"}
    if existing and existing[0]["punya_teks"] and not p.nodes["punya_teks"]:
        return {"kunci": k, "dilewati": "node di graf sudah berteks; dokumen masuk tanpa teks"}

    pairs = [{"dari": r["dari"], "tipe": EDGE_TYPES[r["jenis"]], "ke": r["ke"]} for r in p.relations.values()]
    present = {(x["dari"], x["tipe"], x["ke"]): x["bukti"] for x in client.query(
        "UNWIND $ps AS x MATCH (a:Regulation {key: x.dari})-[e]->(z:Regulation {key: x.ke}) WHERE type(e) = x.tipe "
        "RETURN x.dari AS dari, x.tipe AS tipe, x.ke AS ke, e.evidence AS bukti", ps=pairs)} if pairs else {}
    to_write, skipped = [], []
    for r in p.relations.values():
        edge_key = (r["dari"], EDGE_TYPES[r["jenis"]], r["ke"])
        old_evidence = present.get(edge_key)
        if old_evidence is not None and _EVIDENCE_RANK.get(old_evidence, 9) <= _EVIDENCE_RANK[r["bukti"]]:
            skipped.append(f"{r['dari']} -{r['jenis']}-> {r['ke']}: sudah ada ({old_evidence})")
            continue
        to_write.append((r, old_evidence))

    ts = dt.datetime.now().isoformat(timespec="seconds")
    client.run("MERGE (p:Regulation {key: $k}) SET p += $p, p.stub = false, p.ingested_at = $w",
               k=k, p=graph_props(_clean(p.nodes)), w=ts)
    targets = sorted({x for r, _ in to_write for x in (r["dari"], r["ke"])} - {k})
    new_basis = sorted({x["ke"] for x in p.basis} - set(targets) - {k})
    stubs = []
    for t in targets:
        i = canon_id(t)
        stubs.append({"kunci": t, "jenis": i.kind if i else None, "nomor": i.number if i else None,
                     "tahun": i.year if i else None})
    for t in new_basis:
        i = canon_id(t)
        stubs.append({"kunci": t, "jenis": i.kind if i else None, "nomor": i.number if i else None,
                     "tahun": i.year if i else None})
    if stubs:
        client.run("UNWIND $baris AS b MERGE (p:Regulation {key: b.key}) ON CREATE SET p += b, p.stub = true, "
                   "p.ingested_at = $w", baris=[graph_props(_clean(s)) for s in stubs], w=ts)
    for kind, rel_type in EDGE_TYPES.items():
        rows = [{"dari": r["dari"], "ke": r["ke"],
                 "p": graph_props(_clean({**{x: v for x, v in r.items() if x not in ("dari", "ke")}, "masuk": ts}))}
                for r, _ in to_write if r["jenis"] == kind]
        if rows:
            client.run(f"UNWIND $baris AS b MATCH (a:Regulation {{key: b.dari}}), (z:Regulation {{key: b.ke}}) "
                       f"MERGE (a)-[e:{rel_type}]->(z) SET e += b.p", baris=rows)
    if p.basis:
        client.run("UNWIND $baris AS b MATCH (a:Regulation {key: b.dari}), (z:Regulation {key: b.ke}) "
                   "MERGE (a)-[e:BASED_ON {section: b.p.section}]->(z) SET e += b.p",
                   baris=[{"dari": x["dari"], "ke": x["ke"],
                          "p": graph_props(_clean({**{y: v for y, v in x.items() if y not in ("dari", "ke")}, "masuk": ts}))}
                          for x in p.basis])
    if p.chunks:
        client.run("MATCH (c:Chunk)-[:PART_OF]->(:Regulation {key: $k}) DETACH DELETE c", k=k)
        client.run("UNWIND $baris AS b MATCH (p:Regulation {key: b.peraturan}) MERGE (c:Chunk {id: b.id}) "
                   "SET c += b.p MERGE (c)-[:PART_OF]->(p)",
                   baris=[{"id": c["id"], "peraturan": k, "p": graph_props(_clean(c))} for c in p.chunks])
    n_status = recompute_status(client, [k] + targets, day)
    result = {"kunci": k, "waktu": ts, "node_baru": not existing, "dari_stub": bool(existing and existing[0]["stub"]),
              "edge_ditulis": [f"{r['dari']} -{r['jenis']}-> {r['ke']} ({r['bukti']}"
                               + (f", sebelumnya {b})" if b else ")") for r, b in to_write],
              "edge_dilewati": skipped, "stub_baru_atau_ada": targets + new_basis, "potongan": len(p.chunks),
              "dasar_hukum": len(p.basis),
              "status_dihitung_ulang": n_status, "catatan": p.notes}
    client.run("CREATE (m:Ingest) SET m = $m", m=graph_props({x: (json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v)
                                                             for x, v in {**meta, **result}.items() if v is not None}))
    return result
