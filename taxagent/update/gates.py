from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from .extraction import ExtractionResult
from .llm import LLMResult, finding_leaves, leaves
from .manifest import Manifest, load

NUMBER_SCOPE = load().number_scope
_PASSIVE = {"MENCABUT": "dicabut", "MENCABUT_SEBAGIAN": "dicabut sebagian", "MENGUBAH": "diubah"}

_MONTHS = ["JANUARI", "FEBRUARI", "MARET", "APRIL", "MEI", "JUNI", "JULI", "AGUSTUS",
          "SEPTEMBER", "OKTOBER", "NOVEMBER", "DESEMBER"]


@dataclass
class Effective:
    source: str
    start: str | None = None
    applies_to: list[str] = field(default_factory=list)
    retroactive: bool = False
    transitional: bool = False


def effective_from_text(text: str, source: str) -> Effective:
    from ..monitor.text import extract

    e = extract(text)
    start = e.mulai_berlaku_tanggal
    return Effective(
        source=source,
        start=start if start and re.fullmatch(r"\d{4}-\d{2}-\d{2}", start) else None,
        applies_to=list(e.applies_to),
        retroactive=e.retroaktif,
        transitional=bool(re.search(r"KETENTUAN\s+PERALIHAN", text, re.I)),
    )


@dataclass
class GateContext:
    phase1_keys: list[str] | None = None
    in_force: dict[str, Effective] = field(default_factory=dict)
    llm: LLMResult | None = None
    manifest: Manifest | None = None
    source_status: dict[str, list[tuple[str, str]]] | None = None


@dataclass
class GateResult:
    code: str
    name: str
    passed: bool | None
    reasons: list[str] = field(default_factory=list)

    def fail(self, reason: str) -> None:
        self.passed = False
        self.reasons.append(reason)


def _leaves(value, path: str):
    if isinstance(value, dict):
        for k, v in value.items():
            yield from _leaves(v, f"{path}.{k}")
    elif isinstance(value, list):
        for v in value:
            yield from _leaves(v, f"{path}[]")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        yield path, Decimal(str(value))


def _changed(old, new, path: str):
    if isinstance(new, dict):
        for k, v in new.items():
            yield from _changed(old.get(k) if isinstance(old, dict) else None, v, f"{path}.{k}")
    elif isinstance(new, list):
        for i, v in enumerate(new):
            yield from _changed(old[i] if isinstance(old, list) and i < len(old) else None, v, f"{path}[{i}]")
    elif isinstance(new, (int, float)) and not isinstance(new, bool) and new != old:
        yield path, (Decimal(str(old)) if isinstance(old, (int, float)) else None), Decimal(str(new))


def _structure(old, new) -> str | None:
    if isinstance(old, list) and isinstance(new, list) and len(old) != len(new):
        return f"jumlah lapisan {len(old)} -> {len(new)}"
    if isinstance(old, dict) and isinstance(new, dict) and set(old) != set(new):
        return f"sub-key {sorted(set(old) ^ set(new))}"
    if type(old) is not type(new) and old is not None:
        return f"bentuk {type(old).__name__} -> {type(new).__name__}"
    return None


def effective_year(b: Effective) -> tuple[int | None, str]:
    for p in b.applies_to:
        m = re.match(r"TAHUN PAJAK (\d{4})", p)
        if m:
            return int(m.group(1)), f"berlaku untuk Tahun Pajak {m.group(1)}"
        m = re.match(r"MASA PAJAK ([A-Z]+) (?:TAHUN )?(\d{4})", p)
        if m:
            if m.group(1) == "JANUARI":
                return int(m.group(2)), f"berlaku mulai Masa Pajak Januari {m.group(2)}"
            return None, f"berlaku mulai Masa Pajak {m.group(1).title()} {m.group(2)} (tengah tahun)"
    if b.start:
        if b.start[5:] == "01-01":
            return int(b.start[:4]), f"mulai berlaku {b.start}"
        return None, f"mulai berlaku {b.start} (tengah tahun)"
    return None, "tanggal mulai berlaku tidak terbaca dari teks"


def check_gates(d, results: list[ExtractionResult], context: GateContext | None = None) -> list[GateResult]:
    k = context or GateContext()
    m = k.manifest or load()
    changed = [p for p in d.comparisons if p.status == "berubah"]
    return [
        _g1(d, changed, k.phase1_keys, m),
        _g2(results, k.llm, changed),
        _g3(results, changed),
        _g4(d, results, k.llm, {p.key for p in changed}),
        _g5(changed, m),
        _g6(d, changed, k.in_force, m),
        _g7(changed),
        _g8(changed, k.source_status),
    ]


def _changed_sources(changed) -> list[str]:
    return sorted({s for p in changed for s in p.source})


def _g1(d, changed, keys_fase1: list[str] | None, m: Manifest) -> GateResult:
    g = GateResult("G1", "lingkup dan struktur", True)
    if keys_fase1 is None:
        g.reasons.append("tanpa konteks Fase 1: hanya struktur yang diperiksa")
    else:
        outside = [x for x in keys_fase1 if x not in m.number_scope]
        if outside:
            g.fail(f"key di luar cakupan angka (logika/lampiran), perlu manusia: {', '.join(outside)}")
        status = {p.key: p.status for p in d.comparisons}
        missing = [x for x in keys_fase1 if x in m.number_scope and status.get(x) == "tidak_ditemukan"]
        if missing:
            g.fail(f"ditandai Fase 1 tetapi angkanya tidak terbaca: {', '.join(missing)}")
        unnamed = sorted({p.key for p in changed} - set(keys_fase1))
        if unnamed:
            g.fail(f"angka berubah untuk key yang tidak disebut Fase 1, perlu manusia: {', '.join(unnamed)}")
    for p in d.comparisons:
        if p.status == "konflik":
            g.fail(f"{p.key}: sumber memberi angka berbeda")
    for p in changed:
        s = _structure(p.old, p.new)
        if s:
            g.fail(f"{p.key}: struktur berubah ({s})")
    return g


def _g3(results: list[ExtractionResult], changed) -> GateResult:
    g = GateResult("G3", "angka = terbilang", True)
    verified = set().union(*(h.verified for h in results)) if results else set()
    mismatches = [x for h in results for x in h.mismatches]
    if mismatches:
        g.fail(f"{len(mismatches)} angka di teks digitnya tidak cocok dengan terbilang")
    for p in changed:
        unverified = [f"{j}={b}" for j, _, b in _changed(p.old, p.new, p.key) if b not in verified]
        if unverified:
            g.fail(f"angka berubah tanpa terbilang yang cocok: {', '.join(unverified)}")
    return g


def _g5(changed, m: Manifest) -> GateResult:
    g = GateResult("G5", "kewajaran", True)
    from ..settings import get_settings
    mode = get_settings().g5_mode.lower()
    if mode == "off":
        g.reasons.append("G5 dimatikan (eksperimen)")
        return g
    rmin, rmax = m.ratios
    for p in changed:
        has_old = {j for j, v in _leaves(p.old, p.key) if v} if mode == "ratio" else set()
        for j, v in _leaves(p.new, p.key):
            if j in has_old:
                continue
            r = m.range_for(j)
            if r is None:
                g.fail(f"{j}: tidak ada rentang wajar terdefinisi")
            elif not (r[0] <= v <= r[1]):
                g.fail(f"{j}={v} di luar rentang {r[0]:,}-{r[1]:,}")
        for j, old, new in _changed(p.old, p.new, p.key):
            if old and not (rmin <= new / old <= rmax):
                g.fail(f"{j}: {old} -> {new} (rasio {new / old:.2f}, di luar {rmin}-{rmax}x)")
        group = m.groups.get(p.key)
        for c in (group.consistency if group else ()):
            if c["jenis"] == "kelipatan" and isinstance(p.new, dict):
                small, large = p.new.get(c["kecil"]), p.new.get(c["besar"])
                if small is not None and large is not None and small * c["faktor"] != large:
                    g.fail(f"{p.key}: {c['besar'].replace('_', ' ')} {large:,} != {c['faktor']} x "
                            f"{c['kecil'].replace('_', ' ')} {small:,}")
    return g


def _g6(d, changed, effective: dict[str, Effective], m: Manifest) -> GateResult:
    g = GateResult("G6", "tanggal berlaku", True)
    if not changed:
        return g
    if m.effective_mode != "tahun_pajak":
        g.fail(f"mode berlaku {m.effective_mode!r} belum didukung mesin gerbang")
        return g
    if d.base_year == d.year:
        g.fail(f"tabel tahun {d.year} sudah ada: revisi tabel yang berlaku perlu manusia")
    for s in _changed_sources(changed):
        b = effective.get(s)
        if b is None:
            g.fail(f"{s}: tanggal berlaku tidak tersedia")
            continue
        if b.transitional:
            g.fail(f"{s}: memuat ketentuan peralihan")
        th, note = effective_year(b)
        if th is None:
            g.fail(f"{s}: {note}")
        elif th != d.year:
            g.fail(f"{s}: {note}, bukan tahun pajak draf {d.year}")
        else:
            retro = " (berlaku surut, pemotongan yang sudah terjadi perlu disesuaikan)" if b.retroactive else ""
            g.reasons.append(f"{s}: {note}{retro}")
    return g


def _g7(changed) -> GateResult:
    if not changed:
        return GateResult("G7", "dimuat mesin hitung", None)
    return GateResult("G7", "dimuat mesin hitung", True, ["draf dimuat TabelTarif, lapisan naik"])


def _g8(changed, source_status: dict[str, list[tuple[str, str]]] | None) -> GateResult:
    g = GateResult("G8", "sumber masih berlaku", None)
    if not changed:
        return g
    if source_status is None:
        g.reasons.append("graf peraturan tidak ditanyakan: status sumber tidak diketahui")
        return g
    g.passed = True
    for s in _changed_sources(changed):
        incoming = source_status.get(s)
        if incoming is None:
            g.fail(f"{s}: tidak ada di graf peraturan")
        elif incoming:
            g.fail(f"{s}: " + "; ".join(f"{_PASSIVE.get(t, t.lower())} oleh {n}" for t, n in incoming))
        else:
            g.reasons.append(f"{s}: tidak dicabut/diubah peraturan lain menurut graf")
    return g


def _quote_numbers(text: str) -> set[Decimal]:
    results: set[Decimal] = set()
    for token in re.findall(r"\d[\d.,]*\d|\d", text or ""):
        for reading in (token.replace(",", "."), token.replace(".", "").replace(",", ".")):
            try:
                results.add(Decimal(reading))
            except ArithmeticError:
                continue
    return results


def _g2(results: list[ExtractionResult], llm: LLMResult | None, changed) -> GateResult:
    g = GateResult("G2", "kutipan sumber", True if changed else None)
    det_quotes: dict[str, set[Decimal]] = {}
    for h in results:
        for t in h.findings:
            det_quotes.setdefault(t.key, set()).update(_quote_numbers(t.quote))
    n = 0
    for p in changed:
        for j, _, b in _changed(p.old, p.new, p.key):
            evidence = []
            if b in det_quotes.get(p.key, set()):
                evidence.append("deterministik")
            if llm is not None and j in llm.quotes and llm.values.get(j) == b:
                evidence.append("LLM")
            if not evidence:
                g.fail(f"{j}={b}: tidak ada kutipan teks yang memuat angka ini")
            n += 1
    if changed and g.passed:
        g.reasons.append(f"{n} angka berubah, semuanya punya kutipan teks")
    return g


def _key(path: str) -> str:
    return path.split(".")[0].split("[")[0]


def _g4(d, results: list[ExtractionResult], llm: LLMResult | None, changed_keys: set[str]) -> GateResult:
    g = GateResult("G4", "dua ekstraktor sepakat", None, ["ekstraktor kedua (LLM) tidak dijalankan"])
    if llm is None:
        return g
    if not llm.valid:
        g.passed, g.reasons = False, [f"jawaban LLM tidak valid: {llm.error}"]
        return g
    g.passed, g.reasons = True, []
    det = finding_leaves(results)
    old: dict = {}
    for p in d.comparisons:
        leaves(p.old, p.key, old)
    for j, v in det.items():
        if j not in llm.values:
            if _key(j) in changed_keys:
                g.fail(f"{j}: LLM tidak menemukan angkanya")
        elif llm.values[j] != v:
            g.fail(f"{j}: deterministik {v}, LLM {llm.values[j]}")
    for j, v in llm.values.items():
        if j in det:
            continue
        if j not in old:
            g.fail(f"{j}: LLM membaca {v}, field ini tidak ada di tabel (struktur berubah?)")
        elif old[j] != v:
            g.fail(f"{j}: LLM membaca {v} (tabel {old[j]}), ekstraktor deterministik tidak membacanya")
    if g.passed:
        g.reasons.append(f"{sum(1 for j in det if j in llm.values)} angka dibaca sama oleh kedua ekstraktor")
    return g


def decision(d, gates: list[GateResult]) -> tuple[str, list[str]]:
    reasons = [f"{g.code} {g.name}: " + ("; ".join(g.reasons) or "gagal") for g in gates if g.passed is False]
    if not d.berubah:
        return ("tahan" if reasons else "tidak_ada_perubahan"), reasons
    reasons += [f"{g.code} {g.name}: " + ("; ".join(g.reasons) or "belum dijalankan")
               for g in gates if g.passed is None and g.code != "G7"]
    return ("tahan" if reasons else "siap"), reasons
