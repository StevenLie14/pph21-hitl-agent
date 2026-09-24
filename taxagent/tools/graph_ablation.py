from __future__ import annotations

import re

from pydantic import BaseModel, Field

from . import regulation_graph as G


class PlainSearchArgs(BaseModel):
    query: str = Field(..., description="Pertanyaan atau frasa yang dicari di teks peraturan, mis. 'batas biaya jabatan "
                                        "pegawai tetap' atau 'zakat sebagai pengurang penghasilan'.")
    regulation: str = Field("", description="Batasi pada satu peraturan (opsional), mis. 'PMK 168 Tahun 2023'.")


class PlainArticleArgs(BaseModel):
    regulation: str = Field(..., description="Nomor peraturan, mis. 'PMK 168 Tahun 2023'.")
    article: str = Field(..., description="Nomor pasal saja, mis. '10' atau '32A'.")


@G._safe
def search_text(query: str, regulation: str = "") -> dict:
    q = G._LUCENE.sub(r"\\\1", (query or "").strip())
    if not q:
        return G._error("kueri kosong.")
    key = None
    if regulation:
        node = G._nodes(regulation)
        if not node:
            return G._error(f"'{regulation}' tidak ada di korpus.")
        key = node[0]["kunci"]
    rows, method = G._semantic_rows(query, key), "semantik Gemini"
    if rows is None:
        rows, method = G._bm25_rows(q, key), "full-text BM25"
    result = [{"id": b["id"], "peraturan": b["kunci"], "pasal": b["label"], "halaman_pdf": b["halaman"],
               "tautan": G.page_link(b.get("url_berkas"), b["halaman"]) or b.get("url"), "skor": round(b["score"], 2),
               "teks": b["teks"][:900]} for b in rows[:G.SHOWN]]
    return {"berhasil": True, "metode": method, "hasil": result,
            "sumber": [h["id"] for h in result] + sorted({h["peraturan"] for h in result})}


@G._safe
def get_article(regulation: str, article: str) -> dict:
    node = G._nodes(regulation)
    if not node:
        return G._error(f"'{regulation}' tidak ada di korpus.")
    n = node[0]
    p = re.sub(r"(?i)^pasal\s+", "", str(article).strip())
    chunks = G._client().query("MATCH (c:Chunk)-[:PART_OF]->(:Regulation {key: $k}) WHERE c.article_label STARTS WITH "
                               "'Pasal ' RETURN c.id AS id, c.article_label AS label, c.text AS teks, c.page AS halaman "
                               "ORDER BY c.order LIMIT 400", k=n["kunci"])
    matched = [c for c in chunks if G._article_matches(c["label"], p)]
    if not matched:
        return G._error(f"Pasal {p} tidak ditemukan di {n['kunci']}.")
    page = next((c["halaman"] for c in matched if c.get("halaman")), None)
    return {"berhasil": True, "peraturan": n["kunci"], "pasal": p, "label": [c["label"] for c in matched],
            "teks": "\n".join(c["teks"] for c in matched)[:G.TEXT_LIMIT], "halaman_pdf": page,
            "tautan": G.page_link(n.get("url_berkas"), page) or n.get("url"),
            "sumber": [n["kunci"]] + [c["id"] for c in matched]}


SPECS = [
    (get_article, PlainArticleArgs,
     "Ambil bunyi satu pasal sebuah peraturan beserta halaman PDF. Untuk mengutip bunyi pasal sebagai dasar hukum."),
    (search_text, PlainSearchArgs,
     "Cari pasal peraturan yang relevan dengan pertanyaan (pencarian semantik di seluruh korpus peraturan; boleh "
     "kalimat biasa). Untuk pertanyaan 'peraturan mana yang mengatur X'."),
]
