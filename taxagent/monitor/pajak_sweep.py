from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

from ..corpus.pajak_go_id import LISTING_URL, last_page, parse_listing

FIELDS = ("nomor", "judul", "jenis", "tanggal", "status")
SNAPSHOT_FILE = "sapu_potret.json"
_RE_NOT_IN_FORCE = re.compile(r"^\s*dicabut\s*$|sudah\s+dicabut|tidak\s+berlaku|tidak\s+aktif", re.I)


def load_snapshot(pajak_dir: Path) -> dict[str, dict]:
    f = pajak_dir / SNAPSHOT_FILE
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    result: dict[str, dict] = {}
    if (pajak_dir / "daftar.jsonl").exists():
        for b in (pajak_dir / "daftar.jsonl").read_text(encoding="utf-8").splitlines():
            if b.strip():
                x = json.loads(b)
                result.setdefault(x["slug"], {k: x.get(k, "") for k in FIELDS})
    return result


def save_snapshot(pajak_dir: Path, snapshot: dict[str, dict]) -> None:
    tmp = pajak_dir / (SNAPSHOT_FILE + ".tmp")
    tmp.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    tmp.replace(pajak_dir / SNAPSHOT_FILE)


def sweep(fetch: Callable[[str], bytes], max_pages: int | None = None,
          log: Callable[[str], None] | None = None) -> tuple[list[dict], list[int]]:
    from .sources import SourceError

    html0 = fetch(LISTING_URL.format(0)).decode("utf-8", "ignore")
    last = last_page(html0)
    if max_pages is not None:
        last = min(last, max_pages - 1)
    items, seen, failed = [], set(), []
    for p in range(last + 1):
        try:
            html = html0 if p == 0 else fetch(LISTING_URL.format(p)).decode("utf-8", "ignore")
        except (SourceError, OSError):
            failed.append(p)
            continue
        for x in parse_listing(html):
            if x["slug"] not in seen:
                seen.add(x["slug"])
                items.append({**x, "halaman_listing": p})
        if log and p % 100 == 0:
            log(f"listing pajak.go.id hal {p}/{last}: {len(items)} slug")
    return items, failed


def compare(snapshot: dict[str, dict], items: list[dict]) -> tuple[list[dict], list[tuple[dict, dict[str, tuple]]]]:
    new, changed = [], []
    for x in items:
        old = snapshot.get(x["slug"])
        if old is None:
            new.append(x)
            continue
        diff = {k: (old.get(k, ""), x.get(k, "")) for k in FIELDS if (old.get(k) or "") != (x.get(k) or "")}
        if diff:
            changed.append((x, diff))
    return new, changed


def reason(diff: dict[str, tuple]) -> str:
    return "; ".join(f"{k} pajak.go.id: {a or '-'} -> {b or '-'}" for k, (a, b) in diff.items())


def became_inactive(diff: dict[str, tuple]) -> bool:
    if "status" not in diff:
        return False
    a, b = diff["status"]
    return bool(_RE_NOT_IN_FORCE.search(b or "")) and not _RE_NOT_IN_FORCE.search(a or "")
