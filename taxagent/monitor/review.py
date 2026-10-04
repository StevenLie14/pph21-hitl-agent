from __future__ import annotations

from pathlib import Path

from .resilience import mark_checked
from .run import impact_lines
from .storage import ImpactNote, MonitorState

REVIEW_STATUSES = ("baru", "relevan", "tidak_relevan", "diterapkan")
OPEN_STATUSES = ("baru", "relevan")


def list_notes(state: MonitorState, include_all: bool = False) -> list[tuple[int, ImpactNote]]:
    return [
        (i, c) for i, c in enumerate(state.catatan, start=1)
        if include_all or c.status_review in OPEN_STATUSES
    ]


def mark(
    state: MonitorState,
    number: int,
    new_status: str,
    date: str,
    articles: list[str] | None = None,
    applies_to: list[str] | None = None,
    note: str | None = None,
    provenance_file: Path | None = None,
) -> tuple[ImpactNote, list[str]]:
    if new_status not in REVIEW_STATUSES[1:]:
        raise ValueError(f"status review harus salah satu {REVIEW_STATUSES[1:]}")
    if not 1 <= number <= len(state.catatan):
        raise ValueError(f"nomor catatan {number} di luar 1..{len(state.catatan)}")
    c = state.catatan[number - 1]
    c.status_review = new_status
    c.diterapkan_ke_yaml = new_status == "diterapkan"
    for p in articles or []:
        if p not in c.pasal_terdampak:
            c.pasal_terdampak.append(p)
    for b in applies_to or []:
        if b not in c.berlaku_untuk:
            c.berlaku_untuk.append(b)
    if note:
        c.catatan_review = note
    advanced: list[str] = []
    if new_status in ("tidak_relevan", "diterapkan") and c.key_terdampak:
        advanced = mark_checked(c.key_terdampak, date[:10], provenance_file)
    return c, advanced


def summarize(number: int, c: ImpactNote) -> str:
    lines = [f"#{number} [{c.status_review}] [{c.kategori.upper()}] {c.identitas} (first_seen {c.first_seen[:10]}, {c.sumber})"]
    if c.perihal:
        lines.append(f"    {c.perihal}")
    if c.key_terdampak:
        lines.append(f"    key: {', '.join(c.key_terdampak)}")
    lines += [f"    {x}" for x in impact_lines(c)]
    if c.pasal_terdampak:
        lines.append(f"    pasal: {'; '.join(c.pasal_terdampak)}")
    if c.mulai_berlaku_teks or c.berlaku_untuk:
        lines.append(
            f"    mulai berlaku {c.mulai_berlaku_teks or '?'}"
            + (f", berlaku untuk {', '.join(c.berlaku_untuk)}" if c.berlaku_untuk else "")
            + (" (BERLAKU SURUT)" if c.retroaktif else "")
        )
    for s in c.selisih:
        lines.append(f"    ! {s}")
    if c.catatan_review:
        lines.append(f"    catatan review: {c.catatan_review}")
    return "\n".join(lines)
