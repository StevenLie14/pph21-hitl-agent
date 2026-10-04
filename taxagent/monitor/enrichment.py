from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from .identity import RegulationId
from .jdih import JDIHPage, candidate_slugs, page_url, parse_page
from .text import TextExtraction, extract

Fetcher = Callable[[str], bytes]


@dataclass
class Enrichment:
    page: JDIHPage | None = None
    text: TextExtraction | None = None
    text_url: str | None = None
    discrepancies: list[str] = field(default_factory=list)
    error: list[str] = field(default_factory=list)
    raw_text: str | None = None
    text_source: str | None = None

    def outgoing_relations(self) -> list[tuple[RegulationId, str]]:
        result: list[tuple[RegulationId, str]] = []
        if self.text:
            result += [(p.identitas, "mencabut_sebagian" if p.sebagian else "mencabut") for p in self.text.revokes]
            result += [(i, "mengubah") for i in self.text.amends]
        if self.page:
            result += [(r.identitas, r.jenis_efek) for r in self.page.relasi if r.arah == "keluar" and r.identitas]
        unique: list[tuple[RegulationId, str]] = []
        for i, j in result:
            if all(i != x for x, _ in unique):
                unique.append((i, j))
        return unique


def text_from_file(content: bytes, url: str) -> str:
    if content.lstrip()[:5] == b"%PDF-":
        try:
            import pymupdf
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("PyMuPDF belum terpasang: pip install -e \".[monitor]\"") from exc
        with pymupdf.open(stream=content, filetype="pdf") as doc:
            return "\n".join(p.get_text() for p in doc)
    import html as _html

    t = content.decode("utf-8", errors="ignore")
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S | re.I)
    return _html.unescape(re.sub(r"<[^>]+>", " ", t))


def _read_text(content: bytes, url: str, ocr, errors: list[str]) -> tuple[str, str]:
    is_pdf = content.lstrip()[:5] == b"%PDF-"
    if is_pdf and ocr is not None:
        o = ocr(content)
        if o.text:
            return o.text, o.source
        if o.pdf_kind == "scan":
            errors.append(f"PDF scan tanpa OCR ({o.error or 'OCR tidak tersedia'}); memakai lapisan teks PDF")
    return text_from_file(content, url), ("lapisan_pdf" if is_pdf else "htm")


def choose_text_url(page: JDIHPage) -> str | None:
    def score(u: str) -> int:
        u = u.lower()
        if re.search(r"/api/download/[0-9a-f-]{36}/.+\.pdf$", u):
            return 0
        if u.endswith(".pdf"):
            return 1
        if u.endswith((".htm", ".html")):
            return 2
        return 9
    candidates = sorted((u for u in page.url_unduh if score(u) < 9), key=score)
    return candidates[0] if candidates else None


def _compare(p: Enrichment, ident: RegulationId | None) -> None:
    h, t = p.page, p.text
    if not h or not t:
        return
    for name, from_text, from_portal in (
        ("tanggal penetapan", t.enacted, h.tgl_penetapan),
        ("tanggal pengundangan", t.promulgated, h.tgl_pengundangan),
    ):
        if from_text and from_portal and from_text != from_portal:
            p.discrepancies.append(f"{name}: teks {from_text}, metadata JDIH {from_portal}")
    outgoing = [r for r in h.relasi if r.arah == "keluar" and r.identitas]
    portal_start = next((r.tgl_mulai_berlaku for r in outgoing if r.tgl_mulai_berlaku), None)
    if t.mulai_berlaku_tanggal and portal_start and t.mulai_berlaku_tanggal != portal_start:
        if t.in_force_from == "diundangkan" and not t.promulgated:
            p.discrepancies.append(
                f"mulai berlaku: teks 'pada tanggal diundangkan' = {t.mulai_berlaku_tanggal} (tanggal pengundangan "
                f"dari metadata JDIH), metadata relasi JDIH {portal_start}: dua metadata portal tidak konsisten"
            )
        else:
            p.discrepancies.append(f"mulai berlaku: teks {t.mulai_berlaku_tanggal}, metadata relasi JDIH {portal_start}")

    text_ids = {x.identitas: x for x in t.revokes}
    portal_ids = {r.identitas: r for r in outgoing if r.jenis_efek.startswith("mencabut")}
    for i in text_ids.keys() - portal_ids.keys():
        p.discrepancies.append(f"pencabutan {i} ada di teks tetapi tidak tercatat di relasi JDIH")
    for i in portal_ids.keys() - text_ids.keys():
        if t.chained_revocation:
            p.discrepancies.append(
                f"info: pencabutan {i} tercatat di JDIH; di teks kemungkinan tercakup sebagai perubahan antara "
                "('sebagaimana telah beberapa kali diubah')"
            )
        else:
            p.discrepancies.append(f"pencabutan {i} tercatat di JDIH tetapi tidak ditemukan di teks")
    for i in text_ids.keys() & portal_ids.keys():
        text_partial = text_ids[i].sebagian
        portal_partial = portal_ids[i].jenis_efek == "mencabut_sebagian"
        if text_partial != portal_partial:
            p.discrepancies.append(
                f"pencabutan {i}: teks {'sebagian' if text_partial else 'seluruhnya'}, "
                f"JDIH {'sebagian' if portal_partial else 'seluruhnya'}"
            )
    if t.retroaktif:
        p.discrepancies.append("berlaku surut: mulai berlaku sebelum tanggal pengundangan (periksa pemotongan yang sudah dilakukan)")


def enrich(slug: str, fetch: Fetcher, doc_id: RegulationId | None = None, ocr=None) -> Enrichment:
    p = Enrichment()
    try:
        p.page = parse_page(fetch(page_url(slug)).decode("utf-8", errors="ignore"), page_url(slug))
    except Exception as exc:  # noqa: BLE001
        p.error.append(f"halaman JDIH: {type(exc).__name__}: {exc}")
        return p
    ident = doc_id or p.page.identitas
    p.text_url = choose_text_url(p.page)
    if not p.text_url:
        p.error.append("tidak ada tautan unduh teks di halaman JDIH")
        return p
    try:
        content = fetch(p.text_url)
        p.raw_text, p.text_source = _read_text(content, p.text_url, ocr, p.error)
        p.text = extract(p.raw_text, ident)
    except Exception as exc:  # noqa: BLE001
        p.error.append(f"teks peraturan: {type(exc).__name__}: {exc}")
        return p
    if p.text.unreadable:
        p.error.append(f"tidak terbaca dari teks: {', '.join(p.text.unreadable)}")
    if not p.text.promulgated and not p.text.is_decree and p.page.tgl_pengundangan:
        p.text.promulgated_metadata = p.page.tgl_pengundangan
        p.error.append(
            f"tanggal pengundangan tidak ada di lapisan teks (mis. tanda tangan elektronik); "
            f"dipakai metadata JDIH {p.page.tgl_pengundangan}"
        )
    _compare(p, ident)
    return p


def page_from_id(ident: RegulationId, fetch: Fetcher) -> tuple[str, JDIHPage] | None:
    for slug in candidate_slugs(ident):
        try:
            page = parse_page(fetch(page_url(slug)).decode("utf-8", errors="ignore"), page_url(slug))
        except Exception:  # noqa: BLE001
            continue
        if page.nomor and page.identitas == ident:
            return slug, page
    return None
