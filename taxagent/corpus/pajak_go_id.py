from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Comment, Doctype, NavigableString, ProcessingInstruction, Tag

BASE_URL = "https://www.pajak.go.id"
LISTING_URL = (BASE_URL + "/id/peraturan?title=&field_body_peraturan_value=&field_kategori_peraturan_target_id=All"
               "&field_jenis_dokumen_target_id=All&field_nomor_value=&field_tanggal_peraturan_value%5Bmin%5D="
               "&field_tanggal_peraturan_value%5Bmax%5D=&field_tahun_peraturan_value=All&page={}")

BODY_SELECTORS = (
    ".field--name-field-body-dalam-html",
    ".field--name-field-body-peraturan .field__item",
    ".field--name-field-body .field__item",
    "div.node__content",
)


_BLOCK_TAGS = {"div", "p", "section", "article", "blockquote", "pre", "h1", "h2", "h3", "h4", "h5", "h6",
               "ul", "ol", "li", "dl", "dt", "dd", "table", "thead", "tbody", "tfoot", "caption"}
_DROP_TAGS = {"script", "style", "noscript", "nav", "header", "footer", "aside", "svg", "img"}
_INVISIBLE_SPACE = re.compile("[\u00a0\u2007\u202f\u200b\ufeff]")
_SPACES = re.compile(r"[ \t]+")
_MAX_DEPTH = 200


def _serial(node: Tag, depth: int = 0) -> str:
    if depth >= _MAX_DEPTH:
        return node.get_text(" ")
    parts: list[str] = []
    for child in node.children:
        if isinstance(child, (Comment, Doctype, ProcessingInstruction)):
            continue
        if isinstance(child, NavigableString):
            parts.append(str(child))
            continue
        if not isinstance(child, Tag) or child.name in _DROP_TAGS:
            continue
        if child.name == "br":
            parts.append("\n")
        elif child.name == "tr":
            row = " ".join(s for td in child.find_all(("td", "th"), recursive=False)
                           if (s := _SPACES.sub(" ", _serial(td, depth + 1)).strip()))
            if row:
                parts.append(f"\n{row}\n")
        elif child.name in ("td", "th"):
            if cell := _serial(child, depth + 1).strip():
                parts.append(f" {cell} ")
        elif child.name in _BLOCK_TAGS:
            if block := _serial(child, depth + 1).strip():
                parts.append(f"\n{block}\n")
        else:
            parts.append(_serial(child, depth + 1))
    return "".join(parts)


def render_text(node: Tag | None) -> str:
    if node is None:
        return ""
    text = _INVISIBLE_SPACE.sub(" ", _serial(node))
    text = "\n".join(_SPACES.sub(" ", b).strip() for b in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _text(row: Tag, sel: str) -> str:
    t = row.select_one(sel)
    return re.sub(r"\s+", " ", t.get_text(" ", strip=True)) if t else ""


def slug_from_url(url: str) -> str:
    return urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]


def parse_listing(html: str) -> list[dict]:
    result = []
    for row in BeautifulSoup(html, "html.parser").select("div.peraturan-content"):
        a = row.select_one(".views-field-field-nomor-dokumen a") or row.select_one(".views-field-view-node a")
        if not a or not a.get("href"):
            continue
        url = urljoin(BASE_URL, a["href"]).replace("/index.php/", "/")
        time_el = row.select_one(".views-field-field-tanggal-peraturan time[datetime]")
        result.append({
            "slug": slug_from_url(url),
            "url": url,
            "nomor": _text(row, ".views-field-field-nomor-dokumen"),
            "judul": _text(row, ".views-field-title"),
            "jenis": _text(row, ".views-field-field-jenis-dokumen"),
            "tanggal": time_el["datetime"][:10] if time_el else "",
            "status": _text(row, ".views-field-field-status-peraturan"),
        })
    return result


def last_page(html: str) -> int:
    a = BeautifulSoup(html, "html.parser").select_one("li.pager__item--last a")
    m = re.search(r"page=(\d+)", a["href"]) if a else None
    return int(m.group(1)) if m else 0


def parse_detail(html: str) -> tuple[dict, str]:
    soup = BeautifulSoup(html, "html.parser")
    text = ""
    for sel in BODY_SELECTORS:
        if (node := soup.select_one(sel)) is not None:
            for x in node.select(".sidebar"):
                x.decompose()
            if len(t := render_text(node)) > 100:
                text = t
                break
    attachments = [{"nama": a.get_text(strip=True), "url": urljoin(BASE_URL, a["href"])}
                   for a in soup.select(".field--name-field-lampiran-peraturan .field__item a") if a.get("href")]
    meta = {
        "judul": _text(soup, "h1"),
        "status": _text(soup, ".field--name-field-status-peraturan .field__item"),
        "topik": [t.get_text(strip=True) for t in soup.select(".field--name-field-kategori-peraturan a")],
        "lampiran": attachments,
    }
    return meta, text
