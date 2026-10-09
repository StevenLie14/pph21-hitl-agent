from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
import time
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from taxagent.corpus.pajak_go_id import LISTING_URL, last_page, parse_detail, parse_listing
from taxagent.monitor.sources import SourceError, fetch  # noqa: E402
from taxagent.monitor.text_quality import pdf_kind  # noqa: E402
from taxagent.paths import DATA  # noqa: E402

DEFAULT_DIR = DATA / "korpus_pajak"


def _write(path: Path, content: str | bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    if isinstance(content, bytes):
        tmp.write_bytes(content)
    else:
        tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _log_failure(d: Path, step: str, key: str, error: str) -> None:
    with open(d / "gagal.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"langkah": step, "kunci": key, "galat": error[:300],
                            "waktu": time.strftime("%Y-%m-%d %H:%M:%S")}, ensure_ascii=False) + "\n")


def _safe_url(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, quote(p.path, safe="/%"), p.query, p.fragment))


def load_listing(d: Path) -> dict[str, dict]:
    f = d / "daftar.jsonl"
    if not f.exists():
        return {}
    result: dict[str, dict] = {}
    for line in f.read_text(encoding="utf-8").splitlines():
        if line.strip():
            x = json.loads(line)
            result.setdefault(x["slug"], x)
    return result


def cmd_list(a: argparse.Namespace) -> None:
    known = load_listing(a.dir)
    had_corpus = bool(known)
    last = last_page(fetch(LISTING_URL.format(0)).decode("utf-8", "ignore"))
    print(f"{len(known)} sudah ada, halaman 0..{last}", flush=True)
    new, empty_streak = 0, 0
    with open(a.dir / "daftar.jsonl", "a", encoding="utf-8") as f:
        for p in range(last + 1):
            if had_corpus and empty_streak >= a.stop_after:
                print(f"berhenti di halaman {p}: {empty_streak} halaman berturut-turut tanpa dokumen baru", flush=True)
                break
            try:
                items = parse_listing(fetch(LISTING_URL.format(p)).decode("utf-8", "ignore"))
            except SourceError as exc:
                _log_failure(a.dir, "daftar", str(p), str(exc))
                continue
            new_on_page = 0
            for x in items:
                if x["slug"] not in known:
                    known[x["slug"]] = x
                    f.write(json.dumps(x, ensure_ascii=False) + "\n")
                    new += 1
                    new_on_page += 1
            empty_streak = 0 if new_on_page else empty_streak + 1
            f.flush()
            if p % 50 == 0:
                print(f"hal {p}/{last}: {len(known)} dokumen (+{new})", flush=True)
    print(f"daftar selesai: {len(known)} dokumen, {new} baru", flush=True)


def cmd_detail(a: argparse.Namespace) -> None:
    for sub in ("html", "detail", "teks"):
        (a.dir / sub).mkdir(exist_ok=True)
    listing = load_listing(a.dir)
    pending = [x for s, x in listing.items() if not (a.dir / "detail" / f"{s}.json").exists()]
    print(f"{len(pending)} detail belum diambil", flush=True)
    for i, x in enumerate(pending, 1):
        try:
            html = fetch(_safe_url(x["url"])).decode("utf-8", "ignore")
            meta, text = parse_detail(html)
        except Exception as exc:  # noqa: BLE001
            _log_failure(a.dir, "detail", x["slug"], f"{type(exc).__name__}: {exc}")
            continue
        _write(a.dir / "html" / f"{x['slug']}.html", html)
        if text:
            _write(a.dir / "teks" / f"{x['slug']}.txt", text)
        _write(a.dir / "detail" / f"{x['slug']}.json",
               json.dumps({**x, **meta, "panjang_teks": len(text)}, ensure_ascii=False, indent=1))
        if i % 100 == 0:
            print(f"detail {i}/{len(pending)}", flush=True)
    print("detail selesai", flush=True)


def cmd_attachments(a: argparse.Namespace) -> None:
    details = sorted((a.dir / "detail").glob("*.json"))
    n = 0
    for f in details:
        det = json.loads(f.read_text(encoding="utf-8"))
        if not det.get("lampiran") or all("sha1" in att or "galat" in att for att in det["lampiran"]):
            continue
        folder = a.dir / "lampiran" / f.stem
        folder.mkdir(parents=True, exist_ok=True)
        for i, att in enumerate(det["lampiran"]):
            if "sha1" in att:
                continue
            try:
                content = fetch(_safe_url(att["url"]))
            except SourceError as exc:
                att["galat"] = str(exc)[:200]
                continue
            ext = Path(urlsplit(att["url"]).path).suffix.lower() or ".bin"
            _write(folder / f"{i:02d}{ext}", content)
            att.update(berkas=f"{i:02d}{ext}", sha1=hashlib.sha1(content).hexdigest(), ukuran=len(content))
            if content.lstrip()[:5] == b"%PDF-":
                try:
                    att["jenis"] = pdf_kind(content)
                except Exception as exc:  # noqa: BLE001
                    att["jenis"] = f"rusak: {type(exc).__name__}"
        _write(f, json.dumps(det, ensure_ascii=False, indent=1))
        n += 1
        if n % 100 == 0:
            print(f"lampiran {n} dokumen", flush=True)
    print(f"lampiran selesai: {n} dokumen diproses", flush=True)


def cmd_summary(a: argparse.Namespace) -> None:
    listing = load_listing(a.dir)
    details = [json.loads(f.read_text(encoding="utf-8")) for f in (a.dir / "detail").glob("*.json")] \
        if (a.dir / "detail").exists() else []
    print(f"daftar {len(listing)} | detail {len(details)} | "
          f"teks kosong {sum(1 for d in details if not d['panjang_teks'])}")
    print("\njenis dokumen:")
    for v, n in collections.Counter(x["jenis"] or "-" for x in listing.values()).most_common(25):
        print(f"  {n:6d}  {v}")
    atts = [x for d in details for x in d.get("lampiran", [])]
    print(f"\nlampiran: {len(atts)} berkas, terunduh {sum('sha1' in x for x in atts)}, "
          f"jenis {dict(collections.Counter(x.get('jenis', '-') for x in atts if 'sha1' in x))}")


def main() -> None:
    ap = argparse.ArgumentParser(description='Scrape every pajak.go.id regulation (listing, detail page, attachments) as a supplement to the JDIH corpus.')
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list")
    p.add_argument("--stop-after", dest="stop_after", type=int, default=5,
                   help="Pembaruan: berhenti setelah N halaman berturut-turut tanpa slug baru")
    p.set_defaults(func=cmd_list)
    sub.add_parser("detail").set_defaults(func=cmd_detail)
    sub.add_parser("attachments").set_defaults(func=cmd_attachments)
    sub.add_parser("summary").set_defaults(func=cmd_summary)
    a = ap.parse_args()
    a.dir.mkdir(parents=True, exist_ok=True)
    a.func(a)


if __name__ == "__main__":
    main()
