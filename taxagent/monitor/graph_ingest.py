from __future__ import annotations

import dataclasses
import html as _html
import re
from collections.abc import Callable
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

from ..corpus.ingest import Document, claim_targets, package, parents_from_graph, write
from ..corpus.merge import listing_id as listing_key
from ..corpus.pajak_go_id import LISTING_URL, parse_detail, parse_listing
from .enrichment import choose_text_url
from .jdih import item_listing, page_url, parse_page, search_url

Fetcher = Callable[[str], bytes]


def safe_url(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, quote(p.path, safe="/%"), p.query, p.fragment))


def htm_text(content: bytes) -> str:
    try:
        t = content.decode("utf-8")
    except UnicodeDecodeError:
        t = content.decode("cp1252", errors="replace")
    t = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", " ", t)
    t = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d|dt|dd|center)>", "\n", t)
    t = _html.unescape(re.sub(r"<[^>]+>", " ", t)).replace("\xa0", " ")
    return "\n".join(" ".join(b.split()) for b in t.splitlines() if b.strip())


ALREADY_PRESENT = "sudah ada di graf berteks; berkas tidak diunduh"


def is_complete(client, key: str) -> bool:
    existing = client.query("MATCH (p:Regulation {key: $k}) RETURN p.stub AS stub, p.has_text AS teks, "
                      "p.doc_source AS sumber", k=key)
    return bool(existing) and not existing[0]["stub"] and bool(existing[0]["teks"]) and existing[0].get("sumber") != "pajak"


def from_jdih(slug: str, fetch: Fetcher, ocr=None, skip=None) -> Document | None:
    from .ocr import ocr_if_scanned

    ocr = ocr or ocr_if_scanned
    url = page_url(slug)
    page = parse_page(fetch(url).decode("utf-8", "ignore"), url)
    ident = page.identitas
    if ident is None:
        return None
    record = dataclasses.asdict(page)
    for r in record["relasi"]:
        r["identitas"] = str(r["identitas"]) if r["identitas"] else None
    d = Document(key=str(ident), source="jdih", id=slug, number=page.nomor, title=page.judul, kind=ident.kind,
                 pages=record)
    if skip is not None and skip(d.key):
        d.notes.append(ALREADY_PRESENT)
        return d
    u = choose_text_url(page)
    if u is None:
        d.notes.append("halaman JDIH tanpa tautan berkas")
        return d
    content = fetch(safe_url(u))
    d.file_url = u
    if content.lstrip()[:5] == b"%PDF-":
        import pymupdf

        with pymupdf.open(stream=content, filetype="pdf") as doc:
            d.pdf_pages = doc.page_count
            layer = "\n".join(p.get_text() for p in doc)
        o = ocr(content)
        d.file_kind = o.pdf_kind
        if o.text:
            d.text, d.text_source = o.text, "ocr"
        elif o.pdf_kind == "digital":
            d.text, d.text_source = layer, "lapisan_pdf"
        else:
            d.notes.append(f"PDF scan belum di-OCR ({o.error or 'OCR tidak tersedia'})")
    else:
        text = htm_text(content)
        if len(text.split()) >= 30:
            d.text, d.text_source, d.file_kind = text, "htm_jdih", "htm"
        else:
            d.notes.append("berkas HTM kosong atau halaman galat")
    return d


def latest_pajak(fetch: Fetcher, pages: int = 2) -> list[dict]:
    result, seen = [], set()
    for p in range(pages):
        for x in parse_listing(fetch(LISTING_URL.format(p)).decode("utf-8", "ignore")):
            if x["slug"] not in seen:
                seen.add(x["slug"])
                result.append(x)
    return result


MAX_ATTACHMENTS = 3


def attachment_text(attachments: list[dict], fetch: Fetcher, ocr=None) -> tuple[str | None, str | None, list[str]]:
    from .ocr import ocr_if_scanned

    ocr = ocr or ocr_if_scanned
    parts, sources, notes = [], set(), []
    for att in [x for x in attachments if x.get("url", "").lower().split("?")[0].endswith(".pdf")][:MAX_ATTACHMENTS]:
        from .sources import SourceError

        try:
            content = fetch(safe_url(att["url"]))
        except (SourceError, OSError) as e:
            notes.append(f"lampiran gagal diunduh ({e}): {att.get('nama') or att['url']}")
            continue
        if content.lstrip()[:5] != b"%PDF-":
            notes.append(f"lampiran bukan PDF: {att.get('nama') or att['url']}")
            continue
        o = ocr(content)
        if o.text:
            parts.append(o.text)
            sources.add("lampiran_ocr")
        elif o.pdf_kind == "digital":
            import pymupdf

            with pymupdf.open(stream=content, filetype="pdf") as doc:
                parts.append("\n".join(h.get_text() for h in doc))
            sources.add("lampiran_pdf")
        else:
            notes.append(f"lampiran PDF scan belum di-OCR ({o.error or 'OCR tidak tersedia'}): {att.get('nama')}")
    text = "\n".join(t for t in parts if t.strip())
    if not text:
        return None, None, notes
    return text, ("lampiran_ocr" if "lampiran_ocr" in sources else "lampiran_pdf"), notes


def from_pajak(item: dict, fetch: Fetcher, ocr=None, html: str | None = None) -> Document | None:
    ident = listing_key(item.get("jenis") or "", item.get("nomor") or "")
    if ident is None:
        return None
    meta, text = parse_detail(html if html is not None else fetch(safe_url(item["url"])).decode("utf-8", "ignore"))
    d = Document(key=str(ident), source="pajak", id=item["slug"], number=item.get("nomor") or "",
                 title=meta.get("judul") or item.get("judul") or "", kind=item.get("jenis") or "",
                 detail={**item, **meta}, text=text or None, text_source="pajak.go.id" if text else None)
    if not text:
        t, source, notes = attachment_text(meta.get("lampiran") or [], fetch, ocr)
        d.notes += notes
        if t:
            d.text, d.text_source = t, source
            d.notes.append(f"badan teks pajak.go.id kosong; teks dari lampiran ({source})")
        else:
            d.notes.append("badan teks pajak.go.id kosong dan lampiran tidak memberi teks")
    return d


def local_jdih_index(jdih_dir: Path) -> dict[str, str]:
    import json

    result: dict[str, str] = {}
    for f in sorted((jdih_dir / "daftar").glob("*.jsonl")) if (jdih_dir / "daftar").exists() else []:
        for b in f.read_text(encoding="utf-8").splitlines():
            if not b.strip():
                continue
            x = json.loads(b)
            if x.get("slug") and (k := listing_key(x.get("bentuk") or "", x.get("nomor") or "")):
                result.setdefault(str(k), x["slug"])
    return result


def find_in_jdih(key: str, number: str, fetch: Fetcher, index: dict[str, str] | None = None) -> str | None:
    if index and key in index:
        return index[key]
    for q in dict.fromkeys(x for x in (key, number) if x):
        for x in item_listing(fetch(search_url({"q": q})).decode("utf-8", "ignore")):
            k = listing_key(x.get("bentuk") or "", x.get("nomor") or "")
            if k is not None and str(k) == key and x.get("slug"):
                return x["slug"]
    return None


def pajak_document(item: dict, fetch: Fetcher, index: dict[str, str] | None = None, ocr=None,
                   html: str | None = None) -> Document | None:
    from .sources import SourceError

    ident = listing_key(item.get("jenis") or "", item.get("nomor") or "")
    trace = f"terlihat di pajak.go.id ({item['slug']})"
    if ident is not None:
        try:
            slug = find_in_jdih(str(ident), item.get("nomor") or "", fetch, index)
        except (SourceError, OSError) as e:
            slug, error = None, f"pencarian JDIH gagal ({e})"
        else:
            error = None
        if slug:
            d = from_jdih(slug, fetch, ocr)
            if d is not None:
                d.notes.append(f"{trace}; diambil dari JDIH ({slug}), sumber utama")
                return d
        d = from_pajak(item, fetch, ocr, html)
        if d is not None:
            d.notes.append(error or "tidak ada di JDIH (korpus lokal dan pencarian situs JDIH)")
        return d
    return None


def seen_pajak_slugs(pajak_dir: Path) -> set[str]:
    import json

    f = pajak_dir / "daftar.jsonl"
    if not f.exists():
        return set()
    return {json.loads(b)["slug"] for b in f.read_text(encoding="utf-8").splitlines() if b.strip()}


def corpus_vocabulary(jdih_dir: Path):
    import json

    from ..corpus.quality import Vocabulary

    reference = []
    for f in (jdih_dir / "berkas").glob("*.json"):
        if json.loads(f.read_text(encoding="utf-8")).get("jenis") == "digital":
            t = jdih_dir / "teks" / f"{f.stem}.txt"
            if t.exists():
                reference.append(t.read_text(encoding="utf-8"))
    return Vocabulary(reference)


def ingest(documents: list[Document], client, *, vocabulary=None, dry_run: bool = False, redo: bool = False,
           meta: dict | None = None) -> list[dict]:
    result = []
    for d in documents:
        if not redo:
            existing = client.query("MATCH (p:Regulation {key: $k}) RETURN p.stub AS stub, p.has_text AS teks, "
                              "p.doc_source AS sumber", k=d.key)
            replaces_pajak = bool(existing) and d.source == "jdih" and bool(d.text) and existing[0].get("sumber") == "pajak"
            if existing and not existing[0]["stub"] and (existing[0]["teks"] or not d.text) and not replaces_pajak:
                result.append({"kunci": d.key, "dilewati": "sudah ada di graf"})
                continue
        p = package(d, parents_from_graph(client, claim_targets(d)), vocabulary)
        result.append({**p.summary(), "kering": True} if dry_run
                      else write(client, p, {**(meta or {}), "sumber_masuk": d.source, "id_sumber": d.id}))
    return result
