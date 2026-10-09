from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict
from dataclasses import dataclass, field

EVIDENCED = ("eksplisit", "tersirat")


@dataclass
class Edge:
    source: str
    kind: str
    target: str
    evidence: str
    date: str | None = None
    estimated_date: str | None = None
    via: str | None = None
    affected_articles: list[str] = field(default_factory=list)

    def effective_date(self) -> tuple[dt.date | None, bool]:
        if self.date:
            return dt.date.fromisoformat(self.date), True
        if self.estimated_date:
            return dt.date.fromisoformat(self.estimated_date), False
        return None, False


@dataclass
class Status:
    status: str
    since: str | None = None
    by: list[str] = field(default_factory=list)
    lapsed_articles: list[str] = field(default_factory=list)
    lapsed_paragraphs: dict[str, list[str]] = field(default_factory=dict)
    certain: bool = True
    notes: list[str] = field(default_factory=list)


def split_paragraphs(affected: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    full, paragraphs = set(), {}
    for p in affected:
        m = re.fullmatch(r"(\w+)\((\w+)\)", p)
        if m:
            paragraphs.setdefault(m.group(1), set()).add(m.group(2))
        else:
            full.add(p)
    ordered = sorted(full, key=lambda x: (len(x), x))
    return ordered, {k: sorted(v, key=lambda x: (len(x), x)) for k, v in sorted(paragraphs.items()) if k not in full}


def _in_effect(e: Edge, d: dt.date) -> tuple[bool, bool]:
    t, certain = e.effective_date()
    return (t is None or t <= d), certain


def compute(key: str, date: dt.date, incoming: list[Edge], outgoing: list[Edge], *, start: str | None = None,
            valid_until: str | None = None, pajak_label: str | None = None) -> Status:
    if start and date < dt.date.fromisoformat(start):
        return Status("belum_berlaku", since=None, notes=[f"mulai berlaku {start}"])
    if valid_until and date > dt.date.fromisoformat(valid_until):
        return Status("berakhir", since=valid_until, notes=["peraturan berjangka (fasilitas)"])
    for e in outgoing:
        if e.kind == "ditetapkan_menjadi" and e.evidence in EVIDENCED:
            ok, certain = _in_effect(e, date)
            if ok:
                return Status("ditetapkan_menjadi", since=e.date or e.estimated_date, by=[e.target], certain=certain)
    amends_others = {e.target for e in outgoing if e.kind == "mengubah"}

    def active(kind: str) -> list[tuple[Edge, bool]]:
        result = []
        for e in incoming:
            if e.kind == kind and e.evidence in EVIDENCED:
                ok, certain = _in_effect(e, date)
                if ok:
                    result.append((e, certain))
        return sorted(result, key=lambda x: x[0].effective_date()[0] or dt.date.min)

    revocations = active("mencabut")
    full = [(e, p) for e, p in revocations if e.evidence == "eksplisit" or not (amends_others - {e.via})]
    if full:
        e, certain = full[0]
        st = Status("dicabut", since=e.date or e.estimated_date, by=[x.source for x, _ in full], certain=certain)
        if e.evidence == "tersirat":
            st.notes.append(f"tersirat: ikut dicabut bersama {e.via}")
        if len({x.source for x, _ in full}) > 1:
            st.notes.append("dicabut lebih dari satu peraturan; tanggal paling awal dipakai")
        return st
    partial = active("mencabut_sebagian") + [(e, p) for e, p in revocations if (e, p) not in full]
    if partial:
        st = Status("berlaku_sebagian", since=partial[0][0].date or partial[0][0].estimated_date,
                    by=[e.source for e, _ in partial], certain=all(p for _, p in partial))
        st.lapsed_articles, st.lapsed_paragraphs = split_paragraphs([p for e, _ in partial for p in e.affected_articles])
        if any(e.kind == "mencabut" for e, _ in partial):
            st.notes.append("tersirat lewat pokok, tetapi peraturan ini juga mengubah peraturan lain")
        return st
    amendments = active("mengubah")
    if amendments:
        return Status("berlaku_diubah", since=amendments[-1][0].date or amendments[-1][0].estimated_date,
                      by=[e.source for e, _ in amendments], certain=all(p for _, p in amendments))
    doubtful = [e for e in incoming if e.kind in ("mencabut", "mencabut_sebagian") and e.evidence not in EVIDENCED
                and _in_effect(e, date)[0]]
    if doubtful:
        return Status("tidak_diketahui", by=[e.source for e in doubtful], certain=False,
                      notes=["relasi tercatat di JDIH tetapi buktinya belum ditemukan di teks"])
    if pajak_label == "Dicabut":
        return Status("dicabut", certain=False, notes=["label pajak.go.id; pencabut dan tanggalnya tidak diketahui"])
    return Status("berlaku")


def interval(key: str, incoming: list[Edge], outgoing: list[Edge], *, start: str | None = None,
             valid_until: str | None = None) -> dict:
    amends_others = {e.target for e in outgoing if e.kind == "mengubah"}
    stops = [e.effective_date()[0] for e in incoming if e.kind == "mencabut" and e.evidence in EVIDENCED
             and (e.evidence == "eksplisit" or not (amends_others - {e.via})) and e.effective_date()[0]]
    stops += [e.effective_date()[0] for e in outgoing if e.kind == "ditetapkan_menjadi" and e.evidence in EVIDENCED
              and e.effective_date()[0]]
    if valid_until:
        stops.append(dt.date.fromisoformat(valid_until) + dt.timedelta(days=1))
    return {"berlaku_mulai": start, "berhenti_pada": min(stops).isoformat() if stops else None}


def check_integrity(edges: list[Edge], years: dict[str, int], start: dict[str, str]) -> list[dict]:
    findings = []
    revocations = [e for e in edges if e.kind == "mencabut" and e.evidence in EVIDENCED]
    graph = defaultdict(set)
    for e in revocations:
        graph[e.source].add(e.target)
        if e.source in years and e.target in years and years[e.target] > years[e.source]:
            findings.append({"jenis": "target_lebih_baru", "dari": e.source, "ke": e.target})
        t = e.effective_date()[0]
        if t and start.get(e.target) and t < dt.date.fromisoformat(start[e.target]):
            findings.append({"jenis": "dicabut_sebelum_berlaku", "dari": e.source, "ke": e.target})
    revokers = defaultdict(set)
    for e in revocations:
        if e.evidence == "eksplisit":
            revokers[e.target].add(e.source)
    findings += [{"jenis": "dicabut_penuh_berkali", "ke": k, "oleh": sorted(v)} for k, v in revokers.items() if len(v) > 1]
    for a in list(graph):
        for b in graph[a]:
            if a < b and a in graph.get(b, ()):
                findings.append({"jenis": "siklus_pencabutan", "dari": a, "ke": b})
    return findings
