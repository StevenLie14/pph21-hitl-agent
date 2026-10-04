from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path

import yaml

from ..taxes import get as tax_module
from .classify import Watchlist
from .jdih import JDIHPage
from .storage import MonitorState

DATA_DIR = tax_module().data_dir

PROVENANCE_FILE = DATA_DIR / "provenans.yaml"

CHECKED_LIMIT_DAYS = 183
FACILITY_WINDOW_DAYS = 60
NEXT_RATE_MONTH = 11
QUIET_LIMIT_DAYS = 14
QUEUE_LIMIT_DAYS = 14


def _date(iso: str) -> _dt.date:
    return _dt.date.fromisoformat(iso[:10])


def load_provenance(path: Path | None = None) -> dict[str, dict]:
    data = yaml.safe_load(Path(path or PROVENANCE_FILE).read_text(encoding="utf-8"))
    return data.get("key", {})


def mark_checked(keys: list[str], date: str, path: Path | None = None) -> list[str]:
    p = Path(path or PROVENANCE_FILE)
    text = p.read_text(encoding="utf-8")
    updated = []
    for key in keys:
        rx = re.compile(
            rf'(^  {re.escape(key)}:\n(?:    .*\n)*?    terakhir_dicek: )"([^"]*)"', re.MULTILINE
        )
        m = rx.search(text)
        if not m or m.group(2) >= date:
            continue
        text = text[: m.start()] + f'{m.group(1)}"{date}"' + text[m.end():]
        updated.append(key)
    if updated:
        p.write_text(text, encoding="utf-8")
    return updated


def check_stale(
    state: MonitorState,
    wl: Watchlist,
    now: str,
    provenance: dict[str, dict] | None = None,
    available_years: list[int] | None = None,
) -> list[str]:
    today = _date(now)
    prov = load_provenance() if provenance is None else provenance
    years = tax_module().available_years() if available_years is None else available_years
    warnings: list[str] = []

    for key, info in prov.items():
        checked = info.get("terakhir_dicek")
        if not checked:
            warnings.append(f"key {key} belum pernah dicek terhadap teks resmi")
            continue
        age = (today - _date(checked)).days
        if age > CHECKED_LIMIT_DAYS:
            warnings.append(
                f"key {key} terakhir dicek {checked} ({age} hari lalu); cocokkan lagi dengan {info.get('dasar_hukum')}"
            )

    facilities = [e for e in wl.regulations if e.role == "fasilitas" and e.valid_until]
    if facilities:
        last = max(facilities, key=lambda e: e.valid_until)
        days_left = (_date(last.valid_until) - today).days
        if -FACILITY_WINDOW_DAYS <= days_left <= FACILITY_WINDOW_DAYS:
            status_text = f"berakhir dalam {days_left} hari" if days_left >= 0 else f"sudah berakhir {-days_left} hari lalu"
            warnings.append(
                f"fasilitas terakhir yang diketahui ({last.identity}) {status_text} ({last.valid_until}) "
                "dan belum ada peraturan perpanjangan di watchlist"
            )

    if today.year not in years:
        warnings.append(
            f"tarif_{today.year}.yaml belum ada: perhitungan tahun pajak {today.year} memakai tabel "
            f"{max(years) if years else '?'}; tetapkan apakah ada perubahan lalu buat file (boleh warisi_dari)"
        )
    if today.month >= NEXT_RATE_MONTH and today.year + 1 not in years:
        warnings.append(f"tarif_{today.year + 1}.yaml belum disiapkan menjelang tahun pajak baru")

    if not state.is_empty:
        reference = state.dokumen_baru_terakhir or state.run_terakhir
        if reference:
            quiet_days = (today - _date(reference)).days
            if quiet_days > QUIET_LIMIT_DAYS:
                warnings.append(
                    f"feed JDIH tidak memuat dokumen baru selama {quiet_days} hari (terakhir {reference[:10]}); "
                    "periksa apakah feed masih diperbarui"
                )

    piling = [
        c for c in state.catatan
        if c.status_review == "baru" and (today - _date(c.first_seen)).days > QUEUE_LIMIT_DAYS
    ]
    if piling:
        warnings.append(
            f"{len(piling)} catatan efek belum direview lebih dari {QUEUE_LIMIT_DAYS} hari (pph21 monitor-review)"
        )
    unapplied = [c for c in state.catatan if c.status_review == "relevan" and not c.diterapkan_ke_yaml]
    if unapplied:
        warnings.append(
            f"{len(unapplied)} catatan efek relevan belum diterapkan ke data: "
            + ", ".join(c.identitas for c in unapplied)
        )
    return warnings


def _count(page: JDIHPage, direction: str, kind: str, counterpart: str | None = None) -> int:
    return sum(
        1
        for r in page.relasi
        if r.arah == direction and r.jenis_efek == kind and (counterpart is None or str(r.identitas) == counterpart)
    )


CANARIES = (
    ("PMK 168 Tahun 2023", "keluar", "mencabut", None, 3),
    ("PMK 168 Tahun 2023", "keluar", "mencabut_sebagian", None, 1),
    ("PP 58 Tahun 2023", "keluar", "mencabut_sebagian", "PP 80 Tahun 2010", 1),
    ("PP 80 Tahun 2010", "masuk", "mencabut_sebagian", "PP 58 Tahun 2023", 1),
)


def check_canaries(pages: dict[str, JDIHPage]) -> list[str]:
    failures: list[str] = []
    for key, direction, kind, counterpart, minimum in CANARIES:
        page = pages.get(key)
        if page is None:
            failures.append(f"halaman kanari {key} tidak terbaca")
            continue
        n = _count(page, direction, kind, counterpart)
        if n < minimum:
            failures.append(
                f"{key}: relasi {direction} {kind}{' ' + counterpart if counterpart else ''} terbaca {n}, seharusnya >= {minimum}"
            )
    for key in sorted({k[0] for k in CANARIES}):
        page = pages.get(key)
        if page is not None and not (page.nomor and page.tgl_penetapan):
            failures.append(f"{key}: nomor/tanggal penetapan tidak terbaca dari halaman")
    return failures


def relation_fingerprint(pages: dict[str, JDIHPage]) -> list[str]:
    key: set[str] = set()
    for page in pages.values():
        key.update(page.kunci_relasi)
    return sorted(key)
