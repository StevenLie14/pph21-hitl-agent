from __future__ import annotations

import bisect
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

from ..graph_names import graph_props
from ..monitor.identity import find_all

BASE_URL = "https://www.pajak.go.id"
LISTING_URL = BASE_URL + "/id/faq-page"
MIN_TEXT = 100
_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")


def _soup(html: str):
    from bs4 import BeautifulSoup

    return BeautifulSoup(html, "html.parser")


def slug(url: str) -> str:
    return urlparse(url).path.rstrip("/").rsplit("/", 1)[-1] or hashlib.sha1(url.encode()).hexdigest()[:12]


def fetch_listing(fetch, max_pages: int = 60) -> list[dict]:
    result, seen = [], set()
    for p in range(max_pages):
        s = _soup(fetch(f"{LISTING_URL}?page={p}").decode("utf-8", "replace"))
        a = s.select("div.view-faq-pages td.views-field-title a[href]")
        if not a:
            break
        for x in a:
            url = urljoin(BASE_URL, x["href"])
            if url not in seen:
                seen.add(url)
                result.append({"judul": x.get_text(" ", strip=True), "url": url, "slug": slug(url)})
    return result


def _body(s):
    for sel in ("article.node--type-faq .node__content", "div.node__content", "article"):
        if (b := s.select_one(sel)) is not None:
            return b
    return None


def _date(s) -> str | None:
    for sel, attr in (("meta[property='article:published_time']", "content"), ("time[datetime]", "datetime")):
        if (t := s.select_one(sel)) is not None and t.get(attr):
            return t[attr][:10]
    return None


def parse_detail(html: str, url: str) -> dict:
    s = _soup(html)
    h1 = s.select_one("h1.page-header, h1.page-title, h1")
    b = _body(s)
    text, pdf, images = "", [], []
    if b is not None:
        for x in b.select("script, style, nav"):
            x.decompose()
        for a in b.select("a[href]"):
            u = urljoin(url, a["href"])
            if urlparse(u).path.lower().endswith(".pdf") and u not in pdf:
                pdf.append(u)
        for g in b.select("img[src]"):
            u = urljoin(url, g["src"])
            if urlparse(u).path.lower().endswith(_IMAGE_EXTS) and u not in images:
                images.append(u)
        for x in b.select(".field--name-field-berkas"):
            x.decompose()
        text = b.get_text("\n", strip=True)
    return {"judul": h1.get_text(" ", strip=True) if h1 else "", "tanggal": _date(s), "teks": text,
            "pdf": pdf, "gambar": images}


def _pdf_parts(path: Path) -> list[dict]:
    import pymupdf

    with pymupdf.open(path) as d:
        return [{"jenis": "pdf", "berkas": path.name, "halaman": i, "teks": (t := h.get_text().strip()),
                 "perlu_ocr": len(t) < MIN_TEXT} for i, h in enumerate(d, 1)]


def collect(faq_dir: Path, fetch, log=print) -> dict:
    from ..monitor.sources import SourceError

    for sub in ("html", "lampiran", "gambar", "item"):
        (faq_dir / sub).mkdir(parents=True, exist_ok=True)
    items = fetch_listing(fetch)
    (faq_dir / "daftar.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    counts = {"faq": len(items), "baru": 0, "sudah": 0, "gagal": 0, "perlu_ocr": 0}
    for it in items:
        out_path = faq_dir / "item" / f"{it['slug']}.json"
        if out_path.exists():
            counts["sudah"] += 1
            continue
        html_path = faq_dir / "html" / f"{it['slug']}.html"
        try:
            html = html_path.read_text(encoding="utf-8") if html_path.exists() else fetch(it["url"]).decode("utf-8", "replace")
        except SourceError as e:
            log(f"GAGAL {it['url']}: {e}")
            counts["gagal"] += 1
            continue
        html_path.write_text(html, encoding="utf-8")
        d = parse_detail(html, it["url"])
        parts = [{"jenis": "html", "teks": d["teks"], "perlu_ocr": False}] if d["teks"] else []
        errors = []
        for n, u in enumerate(d["pdf"], 1):
            f = faq_dir / "lampiran" / f"{it['slug']}__{n}.pdf"
            try:
                if not f.exists():
                    f.write_bytes(fetch(u))
                parts += [{**x, "url": u} for x in _pdf_parts(f)]
            except Exception as e:  # noqa: BLE001
                errors.append({"url": u, "galat": f"{type(e).__name__}: {e}"[:200]})
        for n, u in enumerate(d["gambar"], 1):
            f = faq_dir / "gambar" / f"{it['slug']}__{n}{Path(urlparse(u).path).suffix.lower()}"
            try:
                if not f.exists():
                    f.write_bytes(fetch(u))
                parts.append({"jenis": "gambar", "berkas": f.name, "url": u, "teks": "", "perlu_ocr": True})
            except SourceError as e:
                errors.append({"url": u, "galat": str(e)[:200]})
        counts["perlu_ocr"] += sum(x["perlu_ocr"] for x in parts)
        out_path.write_text(json.dumps({**it, "judul": d["judul"] or it["judul"], "tanggal": d["tanggal"],
                                        "diambil": dt.date.today().isoformat(), "bagian": parts, "galat": errors},
                                       ensure_ascii=False, indent=1), encoding="utf-8")
        counts["baru"] += 1
        log(f"{it['slug']}: {len(parts)} bagian, {sum(x['perlu_ocr'] for x in parts)} perlu OCR"
            + (f", {len(errors)} lampiran gagal" if errors else ""))
    return counts


def ocr_file(faq_dir: Path, b: dict) -> Path:
    name = Path(b["berkas"]).stem
    return faq_dir / "ocr" / name / (f"{b['halaman']:04d}.txt" if b["jenis"] == "pdf" else "gambar.txt")


def item_text(faq_dir: Path, item: dict) -> tuple[str, int]:
    pieces, pending = [], 0
    for b in item["bagian"]:
        if b["perlu_ocr"]:
            f = ocr_file(faq_dir, b)
            if f.exists():
                pieces.append(f.read_text(encoding="utf-8"))
            else:
                pending += 1
                if b.get("teks"):
                    pieces.append(b["teks"])
        else:
            pieces.append(b["teks"])
    return "\n".join(x for x in pieces if x.strip()), pending


_RE_QUESTION = re.compile(r"(?m)^\s*(\d{1,3})\s*[.)]\s+(?P<q>[^\n?]{5,600}?(?:\n[^\n?]{1,300}?){0,4}\?)")


def qa_pairs(title: str, text: str) -> list[dict]:
    found = list(_RE_QUESTION.finditer(text))
    ordered = []
    for m in found:
        if not ordered or int(m.group(1)) > int(ordered[-1].group(1)):
            ordered.append(m)
    if len(ordered) >= 2:
        result = []
        for i, m in enumerate(ordered):
            end = ordered[i + 1].start() if i + 1 < len(ordered) else len(text)
            answer = text[m.end():end].strip()
            if answer:
                result.append({"nomor": int(m.group(1)), "pertanyaan": " ".join(m.group("q").split()),
                              "jawaban": answer})
        if len(result) >= 2:
            return result
    return [{"nomor": 0, "pertanyaan": title.strip(), "jawaban": text.strip()}] if text.strip() else []


_RE_NO = re.compile(r"^\d{1,3}\.?$")


def _widest_gap(ws: list, lo: float, hi: float) -> float:
    covered = sorted((max(w[0], lo), min(w[2], hi)) for w in ws if w[2] > lo and w[0] < hi)
    best, x = (0.0, (lo + hi) / 2), lo
    for a, b in covered:
        if a - x > best[0]:
            best = (a - x, (x + a) / 2)
        x = max(x, b)
    if hi - x > best[0]:
        best = (hi - x, (x + hi) / 2)
    return best[1]


def table_qa_pairs(path: Path) -> list[dict]:
    import pymupdf

    words, bounds = [], None
    with pymupdf.open(path) as d:
        for i, h in enumerate(d):
            ws = h.get_text("words")
            heads = {w[4]: w for w in ws if w[4] in ("Pertanyaan", "Jawaban")}
            if len(heads) == 2 and heads["Pertanyaan"][0] < heads["Jawaban"][0]:
                below = heads["Pertanyaan"][3]
                ws = [w for w in ws if w[1] > below]
                left = min((w[0] for w in ws), default=0)
                bounds = (_widest_gap(ws, left, heads["Pertanyaan"][0]), _widest_gap(ws, heads["Pertanyaan"][2],
                                                                                     heads["Jawaban"][0]))
            elif bounds is None:
                continue
            height = h.rect.height
            for w in ws:
                if w[1] < height * 0.06 or w[1] > height * 0.95:
                    continue
                col = 0 if w[0] < bounds[0] else 1 if w[0] < bounds[1] else 2
                words.append((i, round(w[1]), w[0], col, w[4]))
    if bounds is None:
        return []
    words.sort()
    starts, result = [], []
    for h, y, _, col, t in words:
        if col == 0 and _RE_NO.match(t) and (not starts or int(t.rstrip(".")) == result[-1]["nomor"] + 1):
            starts.append((h, y - 3))
            result.append({"nomor": int(t.rstrip(".")), "tanya": [], "jawab": []})
    for h, y, _, col, t in words:
        if col and (j := bisect.bisect_right(starts, (h, y)) - 1) >= 0:
            result[j]["tanya" if col == 1 else "jawab"].append(t)
    return [{"nomor": b["nomor"], "pertanyaan": " ".join(b["tanya"]), "jawaban": " ".join(b["jawab"])}
            for b in result if b["tanya"] and b["jawab"]]


def _item_qa_pairs(faq_dir: Path, it: dict, text: str) -> list[dict]:
    for path in dict.fromkeys(b["berkas"] for b in it["bagian"] if b["jenis"] == "pdf"):
        if len(ps := table_qa_pairs(faq_dir / "lampiran" / path)) >= 2:
            return ps
    return qa_pairs(it["judul"], text)


def _fold(t: str) -> str:
    return " ".join(re.sub(r"[^0-9a-z]+", " ", t.lower()).split())


def pdf_location(faq_dir: Path, it: dict, question: str) -> tuple[str, int] | None:
    key = " ".join(_fold(question).split()[:8])
    if len(key) < 15:
        return None
    for b in it["bagian"]:
        if b["jenis"] != "pdf" or not b.get("url"):
            continue
        f = ocr_file(faq_dir, b)
        text = f.read_text(encoding="utf-8") if b.get("perlu_ocr") and f.exists() else b.get("teks", "")
        if key in _fold(text):
            return b["url"], b["halaman"]
    return None


SPLIT_ABOVE = 2500
PART_TARGET = 1500


def _pieces(text: str, limit: int) -> list[str]:
    out = []
    for para in (x.strip() for x in re.split(r"\n\s*\n|\n(?=\s*(?:\d{1,3}[.)]|[a-z][.)]|[-\u2022*])\s)", text)):
        if not para:
            continue
        if len(para) <= limit:
            out.append(para)
            continue
        for sentence in re.split(r"(?<=[.;:?!])\s+", para):
            while len(sentence) > limit:
                cut = sentence.rfind(" ", 0, limit)
                cut = cut if cut > limit // 2 else limit
                out.append(sentence[:cut].strip())
                sentence = sentence[cut:].strip()
            if sentence:
                out.append(sentence)
    return out


def split_answer(text: str, target: int = PART_TARGET, above: int = SPLIT_ABOVE) -> list[str]:
    text = text.strip()
    if len(text) <= above:
        return [text]
    parts, current = [], ""
    for piece in _pieces(text, target):
        if current and len(current) + 1 + len(piece) > target:
            parts.append(current)
            current = piece
        else:
            current = f"{current}\n{piece}" if current else piece
    if current:
        if parts and len(current) < target // 4:
            parts[-1] = f"{parts[-1]}\n{current}"
        else:
            parts.append(current)
    return parts


def graph_plan(faq_dir: Path) -> tuple[list[dict], list[dict], dict]:
    nodes, refs, summary = [], [], {"halaman": 0, "tanya_jawab": 0, "belum_ocr": 0, "dipecah": 0,
                                    "jawaban_dipotong": 0}
    for f in sorted((faq_dir / "item").glob("*.json")):
        it = json.loads(f.read_text(encoding="utf-8"))
        text, pending = item_text(faq_dir, it)
        summary["halaman"] += 1
        summary["belum_ocr"] += pending
        ps = _item_qa_pairs(faq_dir, it, text)
        summary["dipecah"] += len(ps) > 1
        for p in ps:
            parts = split_answer(p["jawaban"])
            summary["jawaban_dipotong"] += len(parts) > 1
            for n, part in enumerate(parts, 1):
                i = f"{it['slug']}#{p['nomor']}" + (f"-{n}" if len(parts) > 1 else "")
                answer = f"FAQ: {it['judul']}\n{part}" if len(parts) > 1 else part
                pdf_url, pdf_hal = ((len(parts) > 1 and pdf_location(faq_dir, it, part))
                                    or pdf_location(faq_dir, it, p["pertanyaan"]) or ("", 0))
                nodes.append({"id": i, "slug": it["slug"], "nomor": p["nomor"], "judul_halaman": it["judul"],
                              "pertanyaan": p["pertanyaan"], "jawaban": answer, "url": it["url"],
                              "pdf_url": pdf_url, "pdf_halaman": pdf_hal,
                              "bagian_jawaban": n, "jumlah_bagian_jawaban": len(parts),
                              "tanggal": it.get("tanggal"), "diambil": it.get("diambil"),
                              "teks_lengkap": pending == 0, "sumber": "FAQ DJP pajak.go.id"})
                for ident in find_all(f"{it['judul']}\n{p['pertanyaan']}\n{part}"):
                    refs.append({"faq": i, "kunci": str(ident)})
    summary["tanya_jawab"] = sum(n["bagian_jawaban"] == 1 for n in nodes)
    summary["node"] = len(nodes)
    return nodes, refs, summary


SCHEMA_CYPHER = [
    "CREATE CONSTRAINT faq_id IF NOT EXISTS FOR (f:FAQ) REQUIRE f.id IS UNIQUE",
    "CREATE FULLTEXT INDEX faq_text IF NOT EXISTS FOR (f:FAQ) ON EACH [f.question, f.answer, f.page_title]",
]


def write_locations(client, nodes: list[dict]) -> int:
    rows = [{"id": n["id"], "pdf_url": n["pdf_url"], "pdf_halaman": n["pdf_halaman"]} for n in nodes]
    r = client.query("UNWIND $baris AS b MATCH (f:FAQ {id: b.id}) SET f.pdf_url = b.pdf_url, "
                     "f.pdf_page = b.pdf_halaman RETURN count(f) AS n", baris=rows)
    return r[0]["n"]


def write_graph(client, nodes: list[dict], refs: list[dict]) -> dict:
    for c in SCHEMA_CYPHER:
        client.run(c)
    ids = [n["id"] for n in nodes]
    client.run("MATCH (f:FAQ) WHERE NOT f.id IN $ids DETACH DELETE f", ids=ids)
    client.run("UNWIND $baris AS b MERGE (f:FAQ {id: b.id}) SET f = b", baris=[graph_props(n) for n in nodes])
    client.run("MATCH (:FAQ)-[e:CITES]->() DELETE e")
    present = {r["k"] for r in client.query("UNWIND $ks AS k MATCH (p:Regulation {key: k}) RETURN DISTINCT k AS k",
                                            ks=sorted({r["kunci"] for r in refs}))}
    found = [r for r in refs if r["kunci"] in present]
    client.run("UNWIND $baris AS b MATCH (f:FAQ {id: b.faq}), (p:Regulation {key: b.kunci}) MERGE (f)-[:CITES]->(p)",
               baris=found)
    return {"faq": len(nodes), "merujuk": len(found), "rujukan_tidak_di_graf": len(refs) - len(found),
            "kunci_tidak_di_graf": sorted({r["kunci"] for r in refs} - present)}
