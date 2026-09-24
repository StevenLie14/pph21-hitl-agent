from __future__ import annotations

import datetime as dt
import json
import logging
import re
import threading
from urllib.parse import quote

from ..corpus.pages import page_link
from ..corpus.status import Edge, compute
from ..monitor.identity import canon_id_query, find_all, find_all_positions

log = logging.getLogger(__name__)

_local = threading.local()
_neo4j = None
TEXT_LIMIT = 3000
SHOWN = 5
CANDIDATES = 40
ALL_HITS = 100000
IN_FORCE = ("berlaku", "berlaku_diubah", "berlaku_sebagian", "tidak_diketahui")
_REL_TYPES = "['MENCABUT','MENCABUT_SEBAGIAN','MENGUBAH','DITETAPKAN_MENJADI','MEMPERPANJANG','MENGATUR_LEBIH_LANJUT']"
_EDGE_COLUMNS = ("type(e) AS tipe, e.evidence AS bukti, e.source AS sumber, e.effective_date AS tgl, e.estimated_date AS tgl_perkiraan, "
         "e.via AS lewat, e.affected_articles AS pasal_terdampak, e.article AS pasal, e.quote AS kutipan")


class ReadOnlyClient:
    def __init__(self) -> None:
        from neo4j import READ_ACCESS, GraphDatabase

        from ..environment import load_neo4j_env
        from ..settings import get_settings

        load_neo4j_env()
        cfg = get_settings()
        uri, password = cfg.neo4j_v2_uri, cfg.neo4j_v2_password
        if not uri or not password:
            raise RuntimeError("NEO4J_V2_URI dan NEO4J_V2_PASSWORD wajib diset")
        self._mode = READ_ACCESS
        self._driver = GraphDatabase.driver(uri, auth=(cfg.neo4j_v2_user, password))

    def query(self, cypher: str, **params) -> list[dict]:
        with self._driver.session(default_access_mode=self._mode) as s:
            return s.execute_read(lambda tx: [dict(x) for x in tx.run(cypher, **params)])


def use_client(client) -> None:
    _local.client = client


def _client():
    global _neo4j
    injected = getattr(_local, "client", None)
    if injected is not None:
        return injected
    if _neo4j is None:
        _neo4j = ReadOnlyClient()
    return _neo4j


def _error(message: str, hint: str = "") -> dict:
    return {"berhasil": False, "galat": message, "saran": hint}


def _safe(fn):
    def wrapper(**kw) -> dict:
        try:
            return fn(**kw)
        except ValueError as e:
            return _error(str(e), "Perbaiki argumen lalu panggil ulang.")
        except Exception as e:  # noqa: BLE001
            log.warning("regulation graph query failed", exc_info=True)
            return _error(f"graf tidak bisa diakses: {type(e).__name__}: {str(e)[:150]}",
                          "Jawab tanpa graf dan katakan bahwa rujukan graf tidak tersedia.")
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


def _date(date: str) -> dt.date:
    if not (date or "").strip():
        return dt.date.today()
    try:
        return dt.date.fromisoformat(date.strip()[:10])
    except ValueError:
        raise ValueError(f"tanggal '{date}' bukan format YYYY-MM-DD") from None


def _key(regulation: str) -> str | None:
    ident = canon_id_query(regulation or "")
    return str(ident) if ident else None


def _nodes(regulation: str) -> list[dict]:
    k = _key(regulation)
    columns = ("p.key AS kunci, p.title AS judul, p.stub AS stub, p.has_text AS punya_teks, p.start AS mulai, "
             "p.valid_until AS berlaku_sampai, p.pajak_label AS label_pajak, p.url AS url, p.file_url AS url_berkas")
    if k:
        return _client().query(f"MATCH (p:Regulation {{key: $k}}) RETURN {columns}", k=k)
    exact = _client().query(f"MATCH (p:Regulation {{key: $k}}) RETURN {columns}", k=(regulation or "").strip())
    if exact:
        return exact
    q = " ".join((regulation or "").lower().split())
    if len(q) < 4:
        return []
    return _client().query(f"MATCH (p:Regulation) WHERE toLower(p.title) CONTAINS $q RETURN {columns} LIMIT 5", q=q)


def _edges(keys: list[str]) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    incoming = _client().query(f"UNWIND $ks AS k MATCH (a:Regulation)-[e]->(p:Regulation {{key: k}}) WHERE type(e) IN {_REL_TYPES} "
                       f"RETURN k, a.key AS lawan, {_EDGE_COLUMNS} LIMIT 2000", ks=keys)
    outgoing = _client().query(f"UNWIND $ks AS k MATCH (p:Regulation {{key: k}})-[e]->(z:Regulation) WHERE type(e) IN {_REL_TYPES} "
                        f"RETURN k, z.key AS lawan, {_EDGE_COLUMNS} LIMIT 2000", ks=keys)
    m, out_rows = {k: [] for k in keys}, {k: [] for k in keys}
    for r in incoming:
        m[r["k"]].append(r)
    for r in outgoing:
        out_rows[r["k"]].append(r)
    return m, out_rows


def _to_edge(r: dict, incoming_edge: bool, k: str) -> Edge:
    src, dst = (r["lawan"], k) if incoming_edge else (k, r["lawan"])
    return Edge(src, r["tipe"].lower(), dst, r.get("bukti") or "belum_dicek", r.get("tgl"), r.get("tgl_perkiraan"),
                r.get("lewat"), list(r.get("pasal_terdampak") or []))


def _status(n: dict, incoming: list[dict], outgoing: list[dict], d: dt.date) -> dict:
    s = compute(n["kunci"], d, [_to_edge(r, True, n["kunci"]) for r in incoming],
                [_to_edge(r, False, n["kunci"]) for r in outgoing], start=n.get("mulai"),
                valid_until=n.get("berlaku_sampai"), pajak_label=n.get("label_pajak"))
    return {"status": s.status, "sejak": s.since, "oleh": s.by, "pasal_gugur": s.lapsed_articles,
            "ayat_gugur": s.lapsed_paragraphs, "pasti": s.certain, "catatan": s.notes}


def _statuses(keys: list[str], d: dt.date) -> dict[str, dict]:
    node = {n["kunci"]: n for n in _client().query(
        "UNWIND $ks AS k MATCH (p:Regulation {key: k}) RETURN p.key AS kunci, p.start AS mulai, "
        "p.valid_until AS berlaku_sampai, p.pajak_label AS label_pajak", ks=keys)} if keys else {}
    incoming, outgoing = _edges(list(node)) if node else ({}, {})
    return {k: _status(node[k], incoming[k], outgoing[k], d) for k in node}


_basis_cache: dict[tuple, list[dict]] = {}


def basis_status(legal_basis: list[str], date: dt.date) -> list[dict]:
    text = " ".join(legal_basis).upper()
    keys = list(dict.fromkeys([str(i) for i in find_all(text)] +
                               (["UU 7 Tahun 1983"] if re.search(r"\bUU PPH\b", text) else [])))
    if not keys:
        return []
    cacheable = getattr(_local, "client", None) is None
    if cacheable and (cache_key := (tuple(keys), date)) in _basis_cache:
        return _basis_cache[cache_key]
    st = _statuses(keys, date)
    result = [{"peraturan": k, "status": st[k]["status"], "pada": date.isoformat(), "oleh": st[k]["oleh"]}
             for k in keys if k in st]
    if cacheable:
        _basis_cache[(tuple(keys), date)] = result
    return result


_RE_REFERENCE_ARTICLE = re.compile(r"\bPasal\s+(\d+[A-Z]?)\b")
_location_cache: dict[str, dict | None] = {}


def reference_locations(references: list[str]) -> list[dict]:
    cacheable = getattr(_local, "client", None) is None
    result = []
    for r in references:
        if cacheable and r in _location_cache:
            x = _location_cache[r]
        else:
            x = _locate_one(r)
            if cacheable:
                _location_cache[r] = x
        if x:
            result.append(x)
    return result


def _locate_one(r: str) -> dict | None:
    ident = next(iter(find_all(r.upper())), None)
    if ident is None:
        return None
    node = _client().query("MATCH (p:Regulation {key: $k}) RETURN p.url AS url, p.file_url AS url_berkas", k=str(ident))
    if not node:
        return None
    n, m = node[0], _RE_REFERENCE_ARTICLE.search(r)
    page = None
    if m:
        chunks = _client().query("MATCH (c:Chunk)-[:PART_OF]->(:Regulation {key: $k}) WHERE c.article_label STARTS WITH "
                         "'Pasal ' RETURN c.article_label AS label, c.page AS halaman ORDER BY c.order LIMIT 400",
                         k=str(ident))
        page = next((c["halaman"] for c in chunks if c.get("halaman") and _article_matches(c["label"], m.group(1))), None)
    return {"rujukan": r, "peraturan": str(ident), "pasal": m.group(1) if m else None, "halaman_pdf": page,
            "tautan": page_link(n.get("url_berkas"), page) if page else n.get("url") or n.get("url_berkas")}


@_safe
def find_regulation(regulation: str, date: str = "") -> dict:
    d = _date(date)
    node = _nodes(regulation)
    if not node:
        return _error(f"'{regulation}' tidak ada di graf.", "Graf hanya memuat peraturan korpus; jangan mengarang rujukan.")
    incoming, outgoing = _edges([n["kunci"] for n in node])
    result = [{"peraturan": n["kunci"], "judul": n.get("judul"), "teks_tersedia": bool(n.get("punya_teks")),
              "url": n.get("url"), "berkas_pdf": n.get("url_berkas"), **_status(n, incoming[n["kunci"]], outgoing[n["kunci"]], d)} for n in node]
    sumber = [n["kunci"] for n in node] + sorted({x for h in result for x in h["oleh"]})
    return {"berhasil": True, "tanggal": d.isoformat(), "peraturan": result, "sumber": sumber}


@_safe
def amendment_chain(regulation: str, date: str = "") -> dict:
    d = _date(date)
    node = _nodes(regulation)
    if not node:
        return _error(f"'{regulation}' tidak ada di graf.")
    n = node[0]
    incoming, outgoing = _edges([n["kunci"]])

    def row(r: dict) -> dict:
        return {"jenis": r["tipe"].lower(), "peraturan": r["lawan"], "bukti": r.get("bukti"), "sumber": r.get("sumber"),
                "berlaku_efektif": r.get("tgl") or r.get("tgl_perkiraan"), "tanggal_perkiraan": not r.get("tgl"),
                "lewat": r.get("lewat"), "pasal_bukti": r.get("pasal"), "pasal_terdampak": r.get("pasal_terdampak"),
                "kutipan": (r.get("kutipan") or "")[:400]}
    ordered = lambda xs: sorted((row(r) for r in xs), key=lambda x: x["berlaku_efektif"] or "")  # noqa: E731
    m, out_rows = ordered(incoming[n["kunci"]]), ordered(outgoing[n["kunci"]])
    counterparts = _statuses(sorted({x["peraturan"] for x in m + out_rows}), d)
    for x in m + out_rows:
        if x["peraturan"] in counterparts:
            x["status_peraturan"] = counterparts[x["peraturan"]]["status"]
    return {"berhasil": True, "tanggal": d.isoformat(), "peraturan": n["kunci"],
            **_status(n, incoming[n["kunci"]], outgoing[n["kunci"]], d), "diubah_atau_dicabut_oleh": m,
            "mengubah_atau_mencabut": out_rows, "sumber": [n["kunci"]] + [x["peraturan"] for x in m + out_rows]}


@_safe
def regulation_legal_basis(regulation: str, date: str = "") -> dict:
    d = _date(date)
    node = _nodes(regulation)
    if not node:
        return _error(f"'{regulation}' tidak ada di graf.")
    n = node[0]
    basis = _client().query("MATCH (p:Regulation {key: $k})-[e:BASED_ON]->(z:Regulation) RETURN z.key AS kunci, "
                       "z.title AS judul, z.start AS mulai, z.valid_until AS berlaku_sampai, z.pajak_label AS label_pajak, "
                       "e.section AS bagian, e.role AS peran, e.article AS pasal ORDER BY e.order LIMIT 60", k=n["kunci"])
    derived = _client().query("MATCH (a:Regulation)-[e:BASED_ON]->(p:Regulation {key: $k}) WHERE e.role <> 'perubahan' "
                         "RETURN a.key AS kunci, a.title AS judul, a.start AS mulai, a.valid_until AS berlaku_sampai, "
                         "a.pajak_label AS label_pajak, e.section AS bagian, e.article AS pasal, a.year AS tahun "
                         "ORDER BY a.year DESC LIMIT 300", k=n["kunci"])
    unique: dict[str, dict] = {}
    for x in derived:
        if x["kunci"] in unique:
            unique[x["kunci"]]["pasal"] = sorted(set(unique[x["kunci"]]["pasal"] or []) | set(x["pasal"] or []))
        else:
            unique[x["kunci"]] = dict(x)
    derived = list(unique.values())
    keys = sorted({x["kunci"] for x in basis + derived})
    incoming, outgoing = _edges(keys) if keys else ({}, {})
    st = {k: _status(next(x for x in basis + derived if x["kunci"] == k), incoming[k], outgoing[k], d)["status"]
          for k in keys}
    basis_out = [{"peraturan": x["kunci"], "judul": x["judul"], "bagian": x["bagian"], "peran": x["peran"],
                  "pasal": x["pasal"] or [], "status": st[x["kunci"]]} for x in basis]
    in_force = [x for x in derived if st[x["kunci"]] in IN_FORCE]
    derived_out = [{"peraturan": x["kunci"], "judul": x["judul"], "pasal_dasar": x["pasal"] or [],
                    "status": st[x["kunci"]]} for x in in_force[:20]]
    return {"berhasil": True, "tanggal": d.isoformat(), "peraturan": n["kunci"], "dasar": basis_out,
            "pelaksana_berlaku": derived_out, "jumlah_pelaksana": {"semua": len(derived), "berlaku": len(in_force)},
            "sumber": [n["kunci"]] + [x["peraturan"] for x in basis_out + derived_out]}


def _article_matches(label: str, article: str) -> bool:
    m = re.match(r"Pasal (\w+)(?:-(\w+))?", label or "")
    if not m:
        return False
    if m.group(1) == article:
        return True
    a, b = m.group(1), m.group(2)
    return bool(b and a.isdigit() and b.isdigit() and article.isdigit() and int(a) <= int(article) <= int(b))


@_safe
def get_article(regulation: str, article: str, date: str = "") -> dict:
    d = _date(date)
    node = _nodes(regulation)
    if not node:
        return _error(f"'{regulation}' tidak ada di graf.")
    n = node[0]
    p = re.sub(r"(?i)^pasal\s+", "", str(article).strip())
    chunks = _client().query("MATCH (c:Chunk)-[:PART_OF]->(:Regulation {key: $k}) WHERE c.article_label STARTS WITH 'Pasal ' "
                     "RETURN c.id AS id, c.article_label AS label, c.text AS teks, c.page AS halaman ORDER BY c.order "
                     "LIMIT 400", k=n["kunci"])
    matched = [c for c in chunks if _article_matches(c["label"], p)]
    if not matched:
        hint = "Teks per pasal hanya tersedia untuk dokumen pajak berteks." if not chunks else \
            f"Pasal yang ada: {', '.join(dict.fromkeys(c['label'].split(' ayat')[0] for c in chunks))[:300]}"
        return _error(f"Pasal {p} tidak ditemukan di {n['kunci']}.", hint)
    incoming, outgoing = _edges([n["kunci"]])
    st = _status(n, incoming[n["kunci"]], outgoing[n["kunci"]], d)
    warnings = []
    if st["status"] not in IN_FORCE:
        warnings.append(f"{n['kunci']} berstatus {st['status']} pada {d.isoformat()}")
    if p in st["pasal_gugur"]:
        warnings.append(f"Pasal {p} {n['kunci']} sudah dicabut oleh {', '.join(st['oleh'])}")
    elif p in st["ayat_gugur"]:
        clauses = ", ".join(f"({a})" for a in st["ayat_gugur"][p])
        warnings.append(f"Pasal {p} ayat {clauses} {n['kunci']} sudah dicabut oleh {', '.join(st['oleh'])}; "
                          "ayat lain pasal ini masih berlaku")
    page = next((c["halaman"] for c in matched if c.get("halaman")), None)
    return {"berhasil": True, "tanggal": d.isoformat(), "peraturan": n["kunci"], "pasal": p,
            "label": [c["label"] for c in matched], "teks": "\n".join(c["teks"] for c in matched)[:TEXT_LIMIT],
            "halaman_pdf": page, "tautan": page_link(n.get("url_berkas"), page) or n.get("url"),
            "status_peraturan": st["status"], "peringatan": warnings, "sumber": [n["kunci"]] + [c["id"] for c in matched]}


_LUCENE = re.compile(r'([+\-!(){}\[\]^"~*?:\\/]|&&|\|\|)')


@_safe
def search_text(query: str, regulation: str = "", date: str = "", in_force_only: bool = True) -> dict:
    d = _date(date)
    q = _LUCENE.sub(r"\\\1", (query or "").strip())
    if not q:
        return _error("kueri kosong.")
    regulation_key = None
    if regulation:
        node = _nodes(regulation)
        if not node:
            return _error(f"'{regulation}' tidak ada di graf.")
        regulation_key = node[0]["kunci"]
    rows, method = _semantic_rows(query, regulation_key), "semantik Gemini"
    if rows is None:
        rows, method = _bm25_rows(q, regulation_key), "full-text BM25"
    keys = sorted({b["kunci"] for b in rows})
    incoming, outgoing = _edges(keys) if keys else ({}, {})
    statuses = {k: _status(next(b for b in rows if b["kunci"] == k), incoming[k], outgoing[k], d) for k in keys}
    result, dropped = [], 0
    for b in rows:
        st = statuses[b["kunci"]]
        number = re.match(r"Pasal (\w+)", b["label"] or "")
        revoked = bool(number and number.group(1) in st["pasal_gugur"])
        if in_force_only and (st["status"] not in IN_FORCE or revoked):
            dropped += 1
            continue
        result.append({"id": b["id"], "peraturan": b["kunci"], "pasal": b["label"], "halaman_pdf": b["halaman"],
                      "tautan": page_link(b.get("url_berkas"), b["halaman"]) or b.get("url"),
                       "status_peraturan": st["status"], "pasal_gugur": revoked, "skor": round(b["score"], 2),
                       "teks": b["teks"][:900]})
        if number and number.group(1) in st["ayat_gugur"]:
            result[-1]["ayat_gugur"] = st["ayat_gugur"][number.group(1)]
        if len(result) == SHOWN:
            break
    return {"berhasil": True, "tanggal": d.isoformat(), "metode": method, "hasil": result,
            "dibuang_tidak_berlaku": dropped, "sumber": [h["id"] for h in result] + sorted({h["peraturan"] for h in result})}


_CHUNK_COLUMNS = ("RETURN node.id AS id, node.article_label AS label, node.text AS teks, node.page AS halaman, "
                   "score, p.key AS kunci, p.url AS url, p.file_url AS url_berkas, p.start AS mulai, p.valid_until AS berlaku_sampai, "
                   "p.pajak_label AS label_pajak ORDER BY score DESC LIMIT $n")


def _bm25_rows(q: str, key: str | None) -> list[dict]:
    where = "WHERE p.key = $k " if key else ""
    return _client().query("CALL db.index.fulltext.queryNodes('chunk_search', $q, {limit: $lim}) YIELD node, score "
                      "MATCH (node)-[:PART_OF]->(p:Regulation) " + where + _CHUNK_COLUMNS,
                      q=q, n=CANDIDATES, lim=ALL_HITS if key else CANDIDATES, k=key)


def _semantic_rows(query: str, key: str | None) -> list[dict] | None:
    from ..corpus.gemini_embed import query_vector

    v = query_vector(query)
    if v is None:
        return None
    try:
        if key:
            rows = _client().query("MATCH (node:Chunk)-[:PART_OF]->(p:Regulation {key: $k}) "
                               "WHERE node.embedding_gemini IS NOT NULL "
                               "WITH node, p, vector.similarity.cosine(node.embedding_gemini, $v) AS score "
                               + _CHUNK_COLUMNS, k=key, v=v, n=CANDIDATES)
        else:
            rows = _client().query("CALL db.index.vector.queryNodes('chunk_vector_gemini', $lim, $v) YIELD node, score "
                               "MATCH (node)-[:PART_OF]->(p:Regulation) " + _CHUNK_COLUMNS,
                               v=v, n=CANDIDATES * 3, lim=CANDIDATES * 3)
    except Exception:  # noqa: BLE001
        log.info("vector search unavailable", exc_info=True)
        return None
    return rows or None


FAQ_LIMIT = 1500
FAQ_NOTE = ("FAQ DJP adalah penjelasan dari pajak.go.id, BUKAN dasar hukum: jangan memakai angka FAQ untuk "
               "menghitung, dan jangan mengutip peraturan yang disebut FAQ sebelum dicek dengan find_regulation atau "
               "get_article. Sebut sebagai 'FAQ DJP' beserta tautannya.")


@_safe
def search_faq(query: str, date: str = "") -> dict:
    d = _date(date)
    q = _LUCENE.sub(r"\\\1", (query or "").strip())
    if not q:
        return _error("kueri kosong.")
    tail = ("OPTIONAL MATCH (node)-[:CITES]->(p:Regulation) "
            "WITH node, score, collect(p {.kunci, .mulai, .berlaku_sampai, .label_pajak}) AS rujukan "
            "RETURN node.id AS id, node.question AS pertanyaan, node.answer AS jawaban, "
            "node.page_title AS halaman, node.url AS url, node.date AS tanggal_faq, node.pdf_url AS pdf_url, "
            "node.pdf_page AS pdf_halaman, node.answer_part AS bagian, node.answer_parts AS jumlah_bagian, score, rujukan "
            "ORDER BY score DESC")
    from ..corpus.gemini_embed import query_vector

    v, rows, method = query_vector(query), None, "semantik Gemini"
    if v is not None:
        try:
            rows = _client().query("CALL db.index.vector.queryNodes('faq_vector_gemini', $n, $v) YIELD node, score "
                               + tail, v=v, n=SHOWN) or None
        except Exception:  # noqa: BLE001
            log.info("vector index unavailable; full-text search only", exc_info=True)
            rows = None
    if rows is None:
        method = "full-text BM25"
        rows = _client().query("CALL db.index.fulltext.queryNodes('faq_text', $q, {limit: $n}) YIELD node, score " + tail,
                           q=q, n=SHOWN)
    referenced = {r["kunci"]: r for b in rows for r in b["rujukan"]}
    incoming, outgoing = _edges(sorted(referenced)) if referenced else ({}, {})
    statuses = {k: _status(r, incoming[k], outgoing[k], d)["status"] for k, r in referenced.items()}
    result, warnings = [], []
    for b in rows:
        answer = b["jawaban"] or ""
        refs = [{"dirujuk": r["kunci"], "status": statuses[r["kunci"]]} for r in b["rujukan"]]
        stale = [r for r in refs if r["status"] not in IN_FORCE]
        if stale:
            warnings.append(f"FAQ '{b['pertanyaan'][:80]}' merujuk " + ", ".join(
                f"{r['dirujuk']} ({r['status']})" for r in stale) + f" pada {d.isoformat()}: isinya mungkin usang.")
        result.append({"id_faq": b["id"], "pertanyaan": b["pertanyaan"], "jawaban": answer[:FAQ_LIMIT],
                      "jawaban_terpotong": len(answer) > FAQ_LIMIT, "halaman_faq": b["halaman"],
                      "nomor_pertanyaan": faq_number(b["id"]), **faq_location(b),
                      **({"bagian_jawaban": f"{b['bagian']}/{b['jumlah_bagian']}"} if (b.get("jumlah_bagian") or 1) > 1
                         else {}),
                      "tanggal_faq": b["tanggal_faq"], "rujukan_faq": refs, "skor": round(b["score"], 2)})
    return {"berhasil": True, "jenis": "penjelasan FAQ DJP, bukan dasar hukum", "tanggal": d.isoformat(),
            "metode": method, "hasil": result, "peringatan": warnings, "catatan": FAQ_NOTE}


def faq_number(faq_id: str) -> int | None:
    _, _, n = (faq_id or "").partition("#")
    n = n.split("-")[0]
    return int(n) if n.isdigit() else None


def faq_location(b: dict) -> dict:
    if b.get("pdf_url") and b.get("pdf_halaman"):
        return {"tautan": f"{b['pdf_url']}#page={b['pdf_halaman']}", "lampiran_pdf_halaman": b["pdf_halaman"],
                "halaman_faq_web": b["url"]}
    return {"tautan": faq_link(b["url"], b["pertanyaan"])}


def faq_link(url: str, question: str) -> str:
    if not url or not question:
        return url
    opening = " ".join(question.split()[:8])
    return f"{url}#:~:text={quote(opening, safe='')}"


@_safe
def skill_value(key: str, date: str = "") -> dict:
    from ..monitor.resilience import load_provenance
    from ..taxes import get as tax_module

    d = _date(date)
    year = d.year if date else tax_module().default_year()
    try:
        raw = tax_module().load_raw(year)
    except Exception:  # noqa: BLE001
        return _error(f"data tarif tahun {year} tidak tersedia.")
    provenance = load_provenance().get(key, {})
    if key not in raw and not provenance:
        return _error(f"key '{key}' tidak dikenal.", f"Key yang ada: {', '.join(sorted(k for k in raw if k != 'meta'))}")
    definitions = _client().query("MATCH (p:Regulation)-[e:DEFINES]->(:Parameter {name: $k}) RETURN p.key AS kunci, "
                          "p.start AS mulai, p.valid_until AS berlaku_sampai, p.pajak_label AS label_pajak, "
                          "e.article AS pasal LIMIT 20", k=key)
    incoming, outgoing = _edges([x["kunci"] for x in definitions]) if definitions else ({}, {})
    definers, warnings = [], []
    for x in definitions:
        st = _status(x, incoming[x["kunci"]], outgoing[x["kunci"]], d)
        definers.append({"peraturan": x["kunci"], "pasal": x["pasal"] or [], "status": st["status"]})
        if st["status"] not in IN_FORCE:
            warnings.append(f"pendefinisi {x['kunci']} berstatus {st['status']}: nilai kalkulator mungkin usang")
    return {"berhasil": True, "tanggal": d.isoformat(), "key": key, "tahun_pajak": year, "nilai": raw.get(key),
            "dasar_hukum": provenance.get("dasar_hukum"), "terakhir_dicek": provenance.get("terakhir_dicek"),
            "didefinisikan_oleh": definers, "peringatan": warnings, "sumber": [x["kunci"] for x in definitions]}


def parameters_defined_by(key: str) -> list[dict]:
    return _client().query("MATCH (p:Regulation {key: $k})-[e:DEFINES]->(x:Parameter) RETURN x.name AS nama, "
                      "e.article AS pasal LIMIT 100", k=key)


def top_chunks(key: str, kueri: str, n: int = SHOWN) -> list[dict]:
    return _client().query("CALL db.index.fulltext.queryNodes('chunk_search', $q, {limit: $lim}) YIELD node, score "
                      "MATCH (node)-[:PART_OF]->(p:Regulation) WHERE p.key = $k "
                      "RETURN node.id AS id, node.article_label AS label, node.text AS teks, score "
                      "ORDER BY score DESC LIMIT $n", q=kueri, k=key, lim=ALL_HITS, n=n)


_STATUS_WORDS = re.compile(r"dicabut|tidak berlaku|sudah tidak|sebelum(?:nya)?|dulu|lama|digantikan|diganti", re.I)
_STATUS_STATED = re.compile(_STATUS_WORDS.pattern + r"|berakhir|ditetapkan menjadi|disahkan menjadi|tidak lagi|"
                            r"bukan (?:lagi )?(?:aturan|ketentuan|peraturan|dasar hukum)?\s*yang (?:masih )?berlaku|"
                            r"masa berlaku(?:nya)? (?:sudah )?(?:habis|selesai)", re.I)
_CLAIM_IN_FORCE = re.compile(r"(?<!tidak )(?<!sudah tidak )(?<!tidak lagi )(?:masih berlaku|tetap berlaku|"
                             r"berlaku (?:saat ini|sekarang|hingga (?:kini|sekarang)|sampai (?:kini|sekarang)))", re.I)
_SENTENCE_END = re.compile(r"(?<=[.!?])(?<!\bNo\.)(?<!\bno\.)(?<!\bNO\.)(?<!\bNomor\.)(?<!\bhlm\.)(?<!\bHlm\.)"
                           r"(?<!\bhal\.)(?<!\bHal\.)\s+|\n+")
_STATUS_LABEL = {"dicabut": "dicabut", "berakhir": "berakhir", "ditetapkan_menjadi": "ditetapkan menjadi undang-undang",
                 "belum_berlaku": "belum berlaku"}


_RE_ARTICLE_BEFORE = re.compile(r"(?<!PPH )PASAL (\d+[A-Z]?)(?: AYAT \(?(\d+[A-Z]?)\)?)?(?: HURUF [A-Z])?(?: ANGKA \d+)?"
                                r",? (?:(?:DARI|DALAM|PADA) )?(?:(?:PERATURAN|MENTERI|KEUANGAN|PEMERINTAH|UNDANG-UNDANG|"
                                r"DIREKTUR|JENDERAL|PAJAK|KEPUTUSAN|SURAT|EDARAN|PMK|KMK|PP|UU|PERPU|PER|KEP|SE|NOMOR|NO\.?) )*$")


_RE_ARTICLE_AFTER = re.compile(r"^,? PASAL (\d+[A-Z]?)(?: AYAT \(?(\d+[A-Z]?)\)?)?\b")
_ARTICLE_STATUS_WORDS = re.compile(_STATUS_WORDS.pattern + r"|mencabut|pencabutan|dihapus|menghapus", re.I)


def _cited_articles(sentence: str) -> list[tuple[str, str, str | None]]:
    t = re.sub(r"\s+", " ", sentence.upper().replace("*", ""))
    found, used = [], set()
    positions = find_all_positions(t)
    for ident, a, _ in positions:
        m = _RE_ARTICLE_BEFORE.search(t[max(0, a - 80):a])
        if m:
            found.append((str(ident), m.group(1), m.group(2)))
            used.add(max(0, a - 80) + m.start())
    for ident, _, b in positions:
        m = _RE_ARTICLE_AFTER.match(t[b:])
        if m and b + m.group(0).index("PASAL") not in used:
            found.append((str(ident), m.group(1), m.group(2)))
    return list(dict.fromkeys(found))


def _article_in_results(k: str, article: str, tool_results: list[dict]) -> bool:
    pattern = re.compile(rf"\bPASAL {re.escape(article)}\b")
    for h in tool_results:
        if not isinstance(h, dict):
            continue
        text = re.sub(r"\s+", " ", json.dumps(h, ensure_ascii=False, default=str).upper())
        if pattern.search(text) and k in {str(i).upper() for i in find_all(text)} | {str(h.get("peraturan", "")).upper()}:
            return True
    return False


def _check_articles(cited: list[tuple[str, str, str | None, str]], tool_results: list[dict], node: dict,
                    statuses: dict[str, dict], d: dt.date) -> list[str]:
    problems = []
    labels: dict[str, list[str]] = {}
    for k, article, clause, sentence in cited:
        name = f"Pasal {article}" + (f" ayat ({clause})" if clause else "") + f" {k}"
        if not _article_in_results(k.upper(), article, tool_results):
            problems.append(f"{name} disebut tetapi pasal itu tidak muncul di hasil tool di percakapan ini")
            continue
        if k not in node:
            continue
        if k not in labels:
            labels[k] = [c["label"] for c in _client().query(
                "MATCH (c:Chunk)-[:PART_OF]->(:Regulation {key: $k}) WHERE c.article_label STARTS WITH 'Pasal ' "
                "RETURN c.id AS id, c.article_label AS label, c.text AS teks, c.page AS halaman ORDER BY c.order "
                "LIMIT 400", k=k)]
        if labels[k] and not any(_article_matches(x, article) for x in labels[k]):
            problems.append(f"{name}: pasal itu tidak ada di teks {k} pada graf")
            continue
        st = statuses[k]
        if _ARTICLE_STATUS_WORDS.search(sentence):
            continue
        if article in st["pasal_gugur"]:
            problems.append(f"{name}: pasal itu sudah dicabut pada {d.isoformat()} tetapi dikutip tanpa menyebut statusnya")
        elif clause and clause in [str(x) for x in st["ayat_gugur"].get(article, [])]:
            problems.append(f"{name}: ayat itu sudah dicabut pada {d.isoformat()} tetapi dikutip tanpa menyebut statusnya")
    return problems


def _source_text(h: dict) -> str:
    parts = [" ".join(str(x) for x in (h.get("sumber") or [])), str(h.get("dasar_hukum") or ""),
             str(h.get("peraturan") or "")]
    refs = h.get("rujukan")
    if isinstance(refs, list):
        parts += [x for x in refs if isinstance(x, str)]
    parts += [str(x.get("peraturan") or "") for x in (h.get("lokasi_dasar_hukum") or []) if isinstance(x, dict)]
    return " ".join(parts)


def check_citations(answer: str, tool_results: list[dict], tanggal: dt.date | None = None) -> list[str]:
    d = tanggal or dt.date.today()
    known = set()
    for h in tool_results:
        if not isinstance(h, dict):
            continue
        known |= {str(i) for i in find_all(_source_text(h).upper())}
    problems, mentioned, cited = [], [], []
    for sentence in _SENTENCE_END.split(answer or ""):
        for i in find_all(sentence.upper()):
            mentioned.append((str(i), sentence))
        cited += [(k, a, c, sentence) for k, a, c in _cited_articles(sentence)]
    if not mentioned:
        return []
    keys = sorted({k for k, _ in mentioned})
    node = {n["kunci"]: n for n in _client().query(
        "UNWIND $ks AS k MATCH (p:Regulation {key: k}) RETURN p.key AS kunci, p.start AS mulai, "
        "p.valid_until AS berlaku_sampai, p.pajak_label AS label_pajak", ks=keys)}
    incoming, outgoing = _edges(list(node)) if node else ({}, {})
    statuses = {k: _status(node[k], incoming[k], outgoing[k], d) for k in node}
    for k, sentence in mentioned:
        if k not in known:
            problems.append(f"{k} disebut tetapi tidak berasal dari hasil tool di percakapan ini")
            continue
        if k in node:
            st = statuses[k]
            if st["status"] not in IN_FORCE and _CLAIM_IN_FORCE.search(sentence) and not _STATUS_STATED.search(sentence):
                problems.append(f"{k} berstatus {st['status']} pada {d.isoformat()} tetapi disebut masih berlaku")
    problems += _check_articles([x for x in cited if x[0] in known], tool_results, node, statuses, d)
    return list(dict.fromkeys(problems))


def _sentences(answer: str) -> list[tuple[int, int]]:
    spans, start = [], 0
    for m in _SENTENCE_END.finditer(answer):
        spans.append((start, m.start()))
        start = m.end()
    spans.append((start, len(answer)))
    return [(a, b) for a, b in spans if answer[a:b].strip()]


def _states_status(sentence: str, status: str) -> bool:
    low = sentence.lower()
    return bool(_STATUS_STATED.search(sentence)) or status in low or status.replace("_", " ") in low


def unstated_status(answer: str, tanggal: dt.date | None = None) -> list[tuple[str, dict]]:
    d = tanggal or dt.date.today()
    sentences = [answer[a:b] for a, b in _sentences(answer or "")]
    named = {}
    for s in sentences:
        for i in find_all(s.upper()):
            named.setdefault(str(i), []).append(s)
    if not named:
        return []
    statuses = _statuses(list(named), d)
    return [(k, statuses[k]) for k in named if k in statuses and statuses[k]["status"] not in IN_FORCE
            and not any(_states_status(s, statuses[k]["status"]) for s in named[k])]


def _stamp_text(k: str, st: dict, d: dt.date) -> str:
    since = f" sejak {st['sejak']}" if st.get("sejak") else ""
    by = f" oleh {', '.join(st['oleh'])}" if st.get("oleh") else ""
    label = _STATUS_LABEL.get(st["status"], st["status"].replace("_", " "))
    return f"[Status per {d.isoformat()} menurut graf peraturan: {k} {label}{since}{by}.]"


def stamp_status(answer: str, unstated: list[tuple[str, dict]], tanggal: dt.date | None = None) -> str:
    if not unstated:
        return answer
    d = tanggal or dt.date.today()
    spans = _sentences(answer)
    inline: dict[int, list[str]] = {}
    tail: list[str] = []
    for k, st in unstated:
        span = next(((a, b) for a, b in spans if k in {str(i) for i in find_all(answer[a:b].upper())}), None)
        stamp = _stamp_text(k, st, d)
        if span is None or answer[span[0]:span[1]].lstrip().startswith("|"):
            tail.append(stamp)
        else:
            inline.setdefault(span[1], []).append(stamp)
    out = answer
    for end in sorted(inline, reverse=True):
        out = out[:end] + " " + " ".join(inline[end]) + out[end:]
    if tail:
        out = out.rstrip() + "\n\n" + "\n".join(tail)
    return out
