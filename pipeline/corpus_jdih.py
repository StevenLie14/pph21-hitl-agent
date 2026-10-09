from __future__ import annotations

import argparse
import collections
import dataclasses
import hashlib
import json
import sys
import time
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from taxagent.monitor.enrichment import choose_text_url  # noqa: E402
from taxagent.monitor.graph_ingest import htm_text  # noqa: E402,F401
from taxagent.monitor.jdih import BASE_URL, JDIHPage, item_listing, parse_page, search_url  # noqa: E402,F401
from taxagent.monitor.sources import SourceError, fetch  # noqa: E402
from taxagent.monitor.text_quality import pdf_kind  # noqa: E402
from taxagent.paths import DATA  # noqa: E402

DEFAULT_DIR = DATA / "korpus_jdih"
MAX_PAGES = 1000
NON_REGULATIONS = ("Artikel Hukum", "Monografi Hukum", "Putusan Pengadilan")


def _safe_url(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, quote(p.path, safe="/%"), p.query, p.fragment))


def _write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _log_failure(d: Path, step: str, key: str, error: str) -> None:
    with open(d / "gagal.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"langkah": step, "kunci": key, "galat": error[:300],
                            "waktu": time.strftime("%Y-%m-%d %H:%M:%S")}, ensure_ascii=False) + "\n")


def _listing_page(params: dict, p: int) -> list[dict]:
    return item_listing(fetch(search_url(params, p)).decode("utf-8", "ignore"))


def _walk(params: dict, label: str) -> tuple[list[dict], bool]:
    seen: dict[str, dict] = {}
    for p in range(MAX_PAGES + 1):
        items = _listing_page(params, p)
        if not items:
            return list(seen.values()), False
        for x in items:
            seen.setdefault(x["produk_hukum_id"], x)
        if p % 20 == 0:
            print(f"  {label} hal {p}: {len(seen)} dokumen", flush=True)
    return list(seen.values()), True


def cmd_list(a) -> None:
    d = a.dir / "daftar"
    d.mkdir(parents=True, exist_ok=True)
    for year in range(a.to_year, a.from_year - 1, -1):
        f = d / f"{year}.jsonl"
        if f.exists():
            continue
        try:
            items, truncated = _walk({"tahun": year}, str(year))
        except SourceError as e:
            _log_failure(a.dir, "daftar", str(year), str(e))
            print(f"{year}: GAGAL {e}", flush=True)
            continue
        if truncated:
            print(f"PERINGATAN {year}: listing terpotong di halaman {MAX_PAGES}", flush=True)
            _log_failure(a.dir, "daftar", str(year), "listing terpotong (lebih dari 10.010 dokumen)")
        _write(f, "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in items))
        if items:
            print(f"{year}: {len(items)} dokumen", flush=True)
    if a.sweep:
        for order in ("desc", "asc"):
            f = d / f"sapu_{order}.jsonl"
            if f.exists():
                continue
            items, _ = _walk({"order": order}, f"sapu {order}")
            _write(f, "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in items))
    listing = load_listing(a.dir)
    print(f"total unik: {len(listing)} dokumen", flush=True)


def load_listing(d: Path) -> dict[str, dict]:
    listing: dict[str, dict] = {}
    for f in sorted((d / "daftar").glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            x = json.loads(line)
            listing.setdefault(x["produk_hukum_id"], x)
    return listing


def _ordered(listing: dict[str, dict]) -> list[dict]:
    return sorted(listing.values(), key=lambda x: (x.get("bentuk") in NON_REGULATIONS, -(x.get("tahun") or 0)))


def _selection(a) -> list[dict]:
    ordered = _ordered(load_listing(a.dir))
    if not a.only:
        return ordered
    ids = set(a.only.read_text(encoding="utf-8").split())
    return [x for x in ordered if x["produk_hukum_id"] in ids]


def _already_fetched(f: Path, refresh: bool) -> bool:
    if not f.exists():
        return False
    return not refresh or "tgl_mulai_berlaku" in json.loads(f.read_text(encoding="utf-8"))


def cmd_pages(a) -> None:
    d = a.dir / "halaman"
    d.mkdir(parents=True, exist_ok=True)
    pending = [x for x in _selection(a) if x.get("slug") and not _already_fetched(d / f"{x['produk_hukum_id']}.json",
                                                                                   getattr(a, "refresh", False))]
    print(f"{len(pending)} halaman belum diambil", flush=True)
    for k, x in enumerate(pending, 1):
        url = f"{BASE_URL}/dok/{x['slug']}"
        try:
            page = parse_page(fetch(url).decode("utf-8", "ignore"), url)
        except SourceError as e:
            _log_failure(a.dir, "halaman", x["produk_hukum_id"], str(e))
            continue
        record = dataclasses.asdict(page)
        for r in record["relasi"]:
            r["identitas"] = str(r["identitas"]) if r["identitas"] else None
        _write(d / f"{x['produk_hukum_id']}.json", json.dumps(record, ensure_ascii=False))
        if k % 100 == 0:
            print(f"halaman {k}/{len(pending)}", flush=True)
    if not a.only and not a.refresh:
        (a.dir / "halaman_selesai").write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")


def _file_urls(x: dict, d: Path) -> list[str]:
    result = [BASE_URL + x["full_text_pdf"]] if x.get("full_text_pdf") else []
    f = d / "halaman" / f"{x['produk_hukum_id']}.json"
    if f.exists():
        record = json.loads(f.read_text(encoding="utf-8"))
        remaining = list(record.get("url_unduh", []))
        while (u := choose_text_url(JDIHPage(url=record["url"], url_unduh=remaining))) is not None:
            if u not in result:
                result.append(u)
            remaining.remove(u)
    return result


def cmd_download(a) -> None:
    import pymupdf

    for sub in ("pdf", "berkas", "teks"):
        (a.dir / sub).mkdir(parents=True, exist_ok=True)
    pending = [x for x in _selection(a) if not (a.dir / "berkas" / f"{x['produk_hukum_id']}.json").exists()]
    print(f"{len(pending)} dokumen belum diunduh", flush=True)
    for k, x in enumerate(pending, 1):
        i = x["produk_hukum_id"]
        urls = _file_urls(x, a.dir)
        record = {"id": i, "slug": x["slug"], "bentuk": x.get("bentuk"), "url": urls[0] if urls else None}
        if urls:
            content, errors = None, []
            for url in urls:
                try:
                    content = fetch(_safe_url(url), timeout=180)
                    record["url"] = url
                    break
                except SourceError as e:
                    errors.append(str(e))
            if content is None:
                _log_failure(a.dir, "unduh", i, " | ".join(errors))
                continue
            record.update(ukuran=len(content), sha1=hashlib.sha1(content).hexdigest())
            try:
                record["jenis"] = pdf_kind(content)
            except Exception as e:
                record["jenis"], record["galat"] = "rusak", f"{type(e).__name__}: {e}"[:300]
            if record["jenis"] in ("digital", "scan"):
                (a.dir / "pdf" / f"{i}.pdf").write_bytes(content)
                with pymupdf.open(stream=content, filetype="pdf") as doc:
                    record["halaman"] = doc.page_count
                    if record["jenis"] == "digital":
                        _write(a.dir / "teks" / f"{i}.txt", "\n".join(p.get_text() for p in doc))
                        record["sumber_teks"] = "lapisan_pdf"
            elif record["jenis"] is None:
                (a.dir / "pdf" / f"{i}.htm").write_bytes(content)
                text = htm_text(content)
                record["jenis"] = "htm" if len(text.split()) >= 30 else "kosong"
                if record["jenis"] == "htm":
                    _write(a.dir / "teks" / f"{i}.txt", text)
                    record["sumber_teks"] = "htm_jdih"
        elif not (a.dir / "halaman" / f"{i}.json").exists():
            continue
        else:
            record["jenis"] = "tanpa_berkas"
        _write(a.dir / "berkas" / f"{i}.json", json.dumps(record, ensure_ascii=False))
        if k % 50 == 0:
            print(f"unduh {k}/{len(pending)}", flush=True)
    if not a.only and (a.dir / "halaman_selesai").exists():
        (a.dir / "unduh_selesai").write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")


def cmd_summary(a) -> None:
    listing = load_listing(a.dir)
    files = {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in (a.dir / "berkas").glob("*.json")}
    n_pages = len(list((a.dir / "halaman").glob("*.json"))) if (a.dir / "halaman").exists() else 0
    texts = {f.stem for f in (a.dir / "teks").glob("*.txt")} if (a.dir / "teks").exists() else set()
    print(f"daftar {len(listing)} | halaman {n_pages} | berkas {len(files)} | teks {len(texts)}")
    for key in ("bentuk", "teu"):
        print(f"\n{key}:")
        for v, n in collections.Counter(x.get(key) or "-" for x in listing.values()).most_common(25):
            print(f"  {n:6d}  {v}")
    kinds = collections.Counter(b.get("jenis") for b in files.values())
    scan_pages = sum(b.get("halaman", 0) for b in files.values() if b.get("jenis") == "scan")
    scan_done = sum(1 for i, b in files.items() if b.get("jenis") == "scan" and i in texts)
    print(f"\njenis berkas: {dict(kinds)}")
    print(f"scan: {kinds['scan']} PDF, {scan_pages} halaman, sudah OCR {scan_done}")


def main() -> None:
    ap = argparse.ArgumentParser(description='Scrape the whole JDIH Kemenkeu (listing, metadata+relations per document, PDF) as the broad-layer graph corpus.')
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    ap.add_argument("--only", dest="only", type=Path,
                    help="berkas berisi produk_hukum_id (satu per baris): halaman/unduh hanya ini")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list")
    p.add_argument("--from", dest="from_year", type=int, default=1800)
    p.add_argument("--to", dest="to_year", type=int, default=time.localtime().tm_year + 1)
    p.add_argument("--sweep", dest="sweep", action="store_true",
                   help="juga telusuri listing tanpa filter (dokumen tanpa tahun)")
    p.set_defaults(func=cmd_list)
    p = sub.add_parser("pages")
    p.add_argument("--refresh", dest="refresh", action="store_true",
                   help="ambil ulang halaman lama yang belum memuat masa berlaku dan riwayat terakhir")
    p.set_defaults(func=cmd_pages)
    sub.add_parser("download").set_defaults(func=cmd_download)
    sub.add_parser("summary").set_defaults(func=cmd_summary)
    a = ap.parse_args()
    a.dir.mkdir(parents=True, exist_ok=True)
    a.func(a)


if __name__ == "__main__":
    main()
