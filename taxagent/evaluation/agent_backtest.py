from __future__ import annotations

import contextlib
import copy
import datetime as _dt
import json
import os
import re
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from ..taxes import get as tax_module

DATA_DIR = tax_module().data_dir
CASES_FILE = DATA_DIR / "kasus_backtest_agent.yaml"
PHASES = ("basi_hilang", "basi_lanjutan", "sadar", "teradaptasi_asli", "teradaptasi_ubah")
INCOME = 15_000_000
STATUS_TEXT = "sudah kawin dengan 1 anak tanggungan"
STATUS = "K/1"
TER_SOURCE = "PP 58 Tahun 2023"
_NUMBER = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?")


def load_cases(path: Path | None = None) -> list[dict]:
    return yaml.safe_load(Path(path or CASES_FILE).read_text(encoding="utf-8"))["kasus"]


def _profile(case: dict) -> tuple[int, str, str]:
    return int(case.get("gaji", INCOME)), case.get("status", STATUS), case.get("status_teks", STATUS_TEXT)


def question(case: dict, mention: bool = False) -> str:
    y = case["tahun"]
    income, _, status_text = _profile(case)
    salary = f"Rp{income:,}".replace(",", ".")
    if case.get("pertanyaan"):
        q = case["pertanyaan"].format(tahun=y, gaji=salary, status=status_text, golongan=case.get("golongan", ""))
    elif case["jenis"] == "pensiunan_tahunan":
        q = (f"Hitung PPh 21 setahun untuk tahun pajak {y}: pensiunan, {status_text}, uang pensiun {salary} per bulan "
             "selama 12 bulan, tidak ada penghasilan lain, punya NPWP.")
    elif case["jenis"] == "bukan_pegawai":
        q = (f"Saya bukan pegawai dan menerima honor sekali bayar {salary} pada tahun {y}, punya NPWP. Berapa PPh 21 "
             "yang dipotong?")
    elif case["jenis"] == "final":
        q = {"pesangon": f"Saya kena PHK dan menerima pesangon {salary} sekaligus pada tahun {y}. Berapa PPh 21-nya?",
             "honorarium_pns": (f"Saya PNS golongan {case.get('golongan')} dan menerima honorarium dari APBN {salary} "
                                f"pada tahun {y}. Berapa PPh 21 yang dipotong?")}[case["jenis_final"]]
    elif case["jenis"] == "bulanan_ter":
        q = (f"Hitung PPh 21 masa pajak Januari {y} untuk pegawai tetap, {status_text}, gaji {salary} sebulan, "
             "tanpa tunjangan lain, punya NPWP.")
    else:
        q = (f"Hitung PPh 21 setahun untuk tahun pajak {y}: pegawai tetap, {status_text}, gaji {salary} per bulan "
             "selama 12 bulan, tanpa tunjangan lain dan tanpa iuran pensiun, punya NPWP.")
    if mention:
        lead = case.get("kalimat_sadar") or "Saya baca {disebut} {klaim}."
        q = lead.format(disebut=case["disebut"], klaim=case["klaim"]) + " " + q
    return q


def calculation_args(case: dict, year: int) -> tuple[str, dict]:
    income, status, _ = _profile(case)
    kind = case["jenis"]
    if kind == "pensiunan_tahunan":
        return "calculate_pph21_pensioner_annual", {"uang_pensiun": income, "nilai_per_bulan": True,
                                                    "status_ptkp": status, "tahun_pajak": year, "punya_npwp": True}
    if kind == "bukan_pegawai":
        return "calculate_pph21_non_employee", {"penghasilan_bruto": income, "tahun_pajak": year, "punya_npwp": True}
    if kind == "final":
        kw = {"jenis": case["jenis_final"], "jumlah_bruto": income, "tahun_pajak": year, "punya_npwp": True}
        if case.get("golongan"):
            kw["golongan"] = case["golongan"]
        return "calculate_pph21_final", kw
    if kind not in ("tahunan", "bulanan_ter"):
        raise ValueError(f"jenis kasus tidak dikenal: {kind}")
    if kind == "bulanan_ter":
        return "calculate_pph21_permanent_monthly", {"gaji_pokok": income, "status_ptkp": status, "tahun_pajak": year,
                                                     "masa_pajak": 1, "punya_npwp": True}
    return "calculate_pph21_permanent_annual", {"gaji_pokok": income, "nilai_per_bulan": True, "status_ptkp": status,
                                                "tahun_pajak": year, "punya_npwp": True}


def _table(raw: dict, year: int, basis: list[str], sources: dict[str, str] | None = None) -> dict:
    t = copy.deepcopy(raw)
    for key, value in tax_module().load_raw(2024).items():
        if key not in t:
            t[key] = type(value)()
    meta = dict(t.get("meta", {}))
    meta.pop("warisi_dari", None)
    meta.update({"tahun_pajak": year, "berlaku_sejak": f"{year}-01-01", "dasar_hukum": basis,
                 "dasar_hukum_kunci": dict(sources or {})})
    t["meta"] = meta
    return t


def _without_ter(raw: dict) -> dict:
    raw = copy.deepcopy(raw)
    raw["ter_bulanan"] = {}
    return raw


@dataclass
class Plan:
    case: dict
    freeze: _dt.date
    adapted_cut: _dt.date
    stale: dict
    adapted: dict
    adapted_ubah: dict | None
    events: list[str]
    patch_source: str
    keys_reviewed: int
    lead_days: int
    stale_sources: dict[str, str] = field(default_factory=dict)
    adapted_sources: dict[str, str] = field(default_factory=dict)


def own_table(snapshots: list[dict], before: _dt.date, inclusive: bool = False) -> dict:
    best = None
    for snap in snapshots:
        d = None if snap.get("tanggal") is None else _dt.date.fromisoformat(snap["tanggal"])
        if d is None or d < before or (inclusive and d == before):
            best = snap["tabel"]
    if best is None:
        raise ValueError("tabel_sendiri tanpa tabel awal")
    return copy.deepcopy(best)


def ter_counterfactual(raw: dict) -> dict:
    from ..update.evaluation import new_value

    def bump(brackets):
        out = []
        for b in brackets or []:
            b = dict(b)
            if b.get("batas_atas") is not None:
                b["batas_atas"] = new_value(Decimal(str(b["batas_atas"])), "rupiah", False)
            if b.get("persen") is not None:
                b["persen"] = new_value(Decimal(str(b["persen"])), "persen", False)
            out.append(b)
        return out

    raw = copy.deepcopy(raw)
    raw["ter_bulanan"] = {cat: bump(v) for cat, v in (raw.get("ter_bulanan") or {}).items()}
    if isinstance(raw.get("ter_harian"), dict):
        raw["ter_harian"]["lapisan"] = bump(raw["ter_harian"].get("lapisan"))
    return raw


def plan_case(case: dict, docs: dict[str, dict], backtest_runs: list[dict],
              own_tables: list[dict] | None = None) -> Plan:
    from ..update.backtest import _apply, stale_table

    events = case["peristiwa"]
    dates = [docs[e]["tanggal"] for e in events]
    freeze, last = min(dates), max(dates)
    stale = own_table(own_tables, freeze) if own_tables is not None else stale_table(docs, freeze)
    if freeze <= docs[TER_SOURCE]["tanggal"]:
        stale = _without_ter(stale)
    runs = {(r["dokumen"], r["varian"]): r for r in backtest_runs}
    if own_tables is not None:
        adapted, ubah = own_table(own_tables, last, inclusive=True), None
    elif case.get("tabel_teradaptasi"):
        adapted = tax_module().load_raw(int(case["tabel_teradaptasi"].split("_")[1]))
        ubah = ter_counterfactual(adapted)
    else:
        adapted, ubah = copy.deepcopy(stale), copy.deepcopy(stale)
        for e in sorted(events, key=lambda x: docs[x]["tanggal"]):
            _apply(adapted, docs[e]["nilai"])
            mutated = dict(docs[e]["nilai"])
            mutated.update({j: Decimal(v) for j, v in (runs.get((e, "ubah")) or {}).get("mutasi", {}).items()})
            _apply(ubah, mutated)
        if ubah == adapted:
            ubah = None
    ready = all((runs.get((e, "asli")) or {}).get("benar_siap") for e in events if docs[e]["nilai"])
    reviewed = sum(len(docs[e]["nilai"]) for e in events)
    stale_sources = _sources(docs, [n for n, i in docs.items() if i["peran"] in ("awal", "peristiwa")
                                    and i["tanggal"] < freeze])
    return Plan(case, freeze, last + _dt.timedelta(days=1), stale, adapted, ubah, events,
                "sistem" if own_tables is not None else "pipeline" if ready else "manusia", reviewed,
                (_dt.date(case["tahun"], 1, 1) - freeze).days,
                stale_sources, {**stale_sources, **_sources(docs, events)})


def _sources(docs: dict[str, dict], names: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in sorted(names, key=lambda n: docs[n]["tanggal"]):
        group = (docs[name].get("peristiwa") or {}).get("kelompok") or []
        paths = list(docs[name]["nilai"]) + ([group] if isinstance(group, str) else list(group))
        for j in paths:
            out[re.match(r"[a-z_0-9]+", j).group(0)] = name
    return out


def _plain(x):
    if isinstance(x, dict):
        return {k: _plain(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_plain(v) for v in x]
    if isinstance(x, Decimal):
        return int(x) if x == x.to_integral_value() else float(x)
    return x


class FrozenGraph:
    def __init__(self, inner, cut: _dt.date, issued: dict[str, _dt.date | None] | None = None):
        self.inner, self.cut = inner, cut
        self.issued = issued if issued is not None else issue_dates(inner)
        self.hidden = {k for k, d in self.issued.items() if d is not None and d >= cut}

    def _visible(self, x) -> bool:
        if isinstance(x, str):
            return x not in self.hidden
        if isinstance(x, dict):
            return all(self._visible(v) for v in x.values())
        if isinstance(x, (list, tuple)):
            return all(self._visible(v) for v in x)
        return True

    def query(self, cypher: str, **params) -> list[dict]:
        if "faq" in cypher.lower():
            return []
        for name in ("k", "key"):
            if isinstance(params.get(name), str) and params[name] in self.hidden:
                return []
        if isinstance(params.get("ks"), list):
            params = {**params, "ks": [k for k in params["ks"] if k not in self.hidden]}
        return [r for r in self.inner.query(cypher, **params) if self._visible(r)]


def issue_dates(client) -> dict[str, _dt.date | None]:
    rows = client.query("MATCH (p:Regulation) RETURN p.key AS k, p.enacted_on AS e, p.promulgated_on AS p, "
                        "p.year AS y")
    out: dict[str, _dt.date | None] = {}
    for r in rows:
        d = None
        for v in (r.get("e"), r.get("p")):
            with contextlib.suppress(TypeError, ValueError):
                d = d or _dt.date.fromisoformat(str(v)[:10])
        if d is None and r.get("y"):
            d = _dt.date(int(r["y"]), 12, 31)
        out[r["k"]] = d
    return out


def frozen_regulations(cut: _dt.date, issued: dict[str, _dt.date | None]) -> dict:
    from ..monitor.identity import find_all

    raw = yaml.safe_load((DATA_DIR / "regulasi.yaml").read_text(encoding="utf-8"))
    for topic in raw["topik"].values():
        topic["ringkasan"] = ""
        refs = []
        for ref in topic.get("rujukan", []):
            ids = [str(i) for i in find_all(ref.upper())]
            if all((issued.get(i) or _dt.date.min) < cut for i in ids):
                refs.append(ref)
        topic["rujukan"] = refs
    return raw


@contextlib.contextmanager
def world(tables: dict[int, dict], cut: _dt.date, graph_inner=None, issued: dict | None = None):
    from ..monitor import resilience
    from ..tools import regulation_graph as G

    issued = issued if issued is not None else (issue_dates(graph_inner) if graph_inner is not None else {})
    with tempfile.TemporaryDirectory(prefix="backtest_agent_") as tmp:
        d = Path(tmp)
        for y, t in tables.items():
            (d / f"tarif_{y}.yaml").write_text(yaml.safe_dump(_plain(t), allow_unicode=True, sort_keys=False),
                                               encoding="utf-8")
        (d / "regulasi.yaml").write_text(yaml.safe_dump(frozen_regulations(cut, issued), allow_unicode=True),
                                         encoding="utf-8")
        saved = (resilience.load_provenance, G._neo4j, os.environ.get("PPH21_PERMINTAAN_AGENT"))
        tax_module().use_data_dir(d)
        resilience.load_provenance = lambda path=None: {}
        if graph_inner is not None:
            G._neo4j = FrozenGraph(graph_inner, cut, issued)
        os.environ["PPH21_PERMINTAAN_AGENT"] = str(d / "permintaan_agent.jsonl")
        _clear_caches()
        try:
            yield d
        finally:
            tax_module().use_data_dir(None)
            resilience.load_provenance, G._neo4j = saved[:2]
            if saved[2] is None:
                os.environ.pop("PPH21_PERMINTAAN_AGENT", None)
            else:
                os.environ["PPH21_PERMINTAAN_AGENT"] = saved[2]
            _clear_caches()


def _clear_caches() -> None:
    from ..tools import regulation_graph as G

    G._basis_cache.clear()


def phase_world(plan: Plan, phase: str) -> tuple[dict[int, dict], _dt.date]:
    y, prev = plan.case["tahun"], plan.case["tahun"] - 1
    old_basis = ["(tabel sebelum perubahan)"]
    stale = {prev: _table(plan.stale, prev, old_basis, plan.stale_sources)}
    if phase == "basi_hilang":
        return stale, plan.freeze
    if phase in ("basi_lanjutan", "sadar"):
        return {**stale, y: _table(plan.stale, y, old_basis, plan.stale_sources)}, plan.freeze
    table = plan.adapted if phase == "teradaptasi_asli" else plan.adapted_ubah
    return {**stale, y: _table(table, y, list(plan.events), plan.adapted_sources)}, plan.adapted_cut


def engine_result(case: dict, year: int) -> Decimal | None:
    name, kw = calculation_args(case, year)
    fn = next(f for f, _, _ in tax_module().tool_specs() if f.__name__ == name)
    r = fn(**kw)
    return Decimal(str(r["pph_terutang"])) if r.get("berhasil") else None


def answer_numbers(text: str) -> set[int]:
    return {int(m.group(0).split(",")[0].replace(".", "")) for m in _NUMBER.finditer(text or "")}


@dataclass
class PhaseRun:
    kasus: str
    fase: str
    ulang: int
    pertanyaan: str
    jawaban: str = ""
    tool: list[str] = field(default_factory=list)
    melapor: bool = False
    alasan_lapor: list[str] = field(default_factory=list)
    hitung: list[dict] = field(default_factory=list)
    angka_benar: bool = False
    angka_lama: bool = False
    angka_baru: bool = False
    angka_asli_di_ubah: bool = False
    sebut_peristiwa: bool = False
    tanggapi_klaim: bool = False
    anakronis: list[str] = field(default_factory=list)
    putaran: int = 0
    detik: float = 0.0
    token_masuk: int = 0
    token_keluar: int = 0
    koreksi_sitasi: list[str] = field(default_factory=list)
    status_distempel: list[str] = field(default_factory=list)
    galat: str | None = None
    hasil: str = ""


def outcome(r: PhaseRun) -> str:
    if r.galat:
        return "galat"
    if r.fase.startswith("teradaptasi"):
        if r.angka_benar:
            return "benar"
        if r.fase == "teradaptasi_ubah" and r.angka_asli_di_ubah:
            return "ingatan"
        if r.melapor:
            return "melapor_keliru"
        return "salah" if r.hitung or r.angka_lama or r.angka_baru else "tanpa_angka"
    if r.angka_baru and not r.melapor:
        return "angka_baru_tanpa_lapor"
    if r.melapor:
        return "melapor_dengan_angka" if (r.angka_lama or r.angka_baru) else "melapor"
    if r.angka_lama:
        return "angka_lama_dengan_catatan" if r.tanggapi_klaim else "angka_lama_diam"
    return "tanpa_angka"


def score(r: PhaseRun, turn, expected: dict[str, Decimal | None], events: list[str], tax_year: int,
          issued: dict[str, _dt.date | None], claim: str = "") -> None:
    from ..monitor.identity import canon_id, find_all

    r.jawaban = turn.answer
    r.tool = [j.name for j in turn.trace]
    r.putaran = turn.rounds
    r.token_masuk = int(getattr(turn, "tokens_in", 0) or 0)
    r.token_keluar = int(getattr(turn, "tokens_out", 0) or 0)
    r.koreksi_sitasi = list(getattr(turn, "citation_corrections", []) or [])
    r.status_distempel = list(getattr(turn, "status_stamped", []) or [])
    for j in turn.trace:
        res = j.result if isinstance(j.result, dict) else {}
        if j.name == "report_possibly_stale" and res.get("berhasil"):
            r.melapor = True
            args = j.arguments or {}
            r.alasan_lapor.append(("otomatis:" if args.get("otomatis") else "") + str(args.get("reason") or args.get("alasan")))
        if j.name.startswith("calculate_") and res.get("berhasil"):
            r.hitung.append({"tahun_pajak": res.get("tahun_pajak"), "pph": res.get("pph_terutang")})
    nums = answer_numbers(turn.answer)

    def has(x: Decimal | None) -> bool:
        return x is not None and int(x) in nums

    r.angka_benar = has(expected.get("dunia"))
    r.angka_lama = has(expected.get("lama"))
    r.angka_baru = has(expected.get("baru")) and expected.get("baru") != expected.get("lama")
    r.angka_asli_di_ubah = r.fase == "teradaptasi_ubah" and has(expected.get("baru"))
    named = [str(i) for i in find_all((turn.answer or "").upper())]
    event_ids = {str(canon_id(e)) for e in events}
    r.sebut_peristiwa = bool(event_ids & set(named))
    if claim:
        r.tanggapi_klaim = r.sebut_peristiwa or bool(answer_numbers(claim) & nums)
    r.anakronis = sorted({i for i in named if (d := issued.get(i)) and d.year > tax_year})
    r.hasil = outcome(r)


def run(cases: list[dict], make_agent: Callable[[], Any], graph_inner, backtest_runs: list[dict],
        phases: tuple[str, ...] = PHASES, repeats: int = 1, progress: Callable[[PhaseRun], None] | None = None,
        own_tables: list[dict] | None = None) -> dict:
    from ..update.backtest import documents, load_events
    from ..update.evaluation import load_labels

    docs = documents(load_events(), load_labels())
    issued = issue_dates(graph_inner) if graph_inner is not None else {}
    plans, runs = [], []
    for case in cases:
        plan = plan_case(case, docs, backtest_runs, own_tables)
        y = case["tahun"]
        with world({y: _table(plan.adapted, y, list(plan.events))}, plan.adapted_cut, None, issued):
            new = engine_result(case, y)
        with world({y: _table(plan.stale, y, [])}, plan.freeze, None, issued):
            old = engine_result(case, y)
        info = {"kasus": case["id"], "tahun": y, "peristiwa": plan.events, "beku": plan.freeze.isoformat(),
                "potong_teradaptasi": plan.adapted_cut.isoformat(), "sumber_patch": plan.patch_source,
                "kunci_ditinjau": plan.keys_reviewed, "jeda_hari": plan.lead_days,
                "pph_lama": None if old is None else str(old), "pph_baru": None if new is None else str(new),
                "sebagian": bool(case.get("sebagian"))}
        allowed = set(case.get("fase") or PHASES)
        for phase in phases:
            if phase not in allowed:
                continue
            if phase == "teradaptasi_ubah" and plan.adapted_ubah is None:
                continue
            tables, cut = phase_world(plan, phase)
            with world(tables, cut, graph_inner, issued):
                expected = {"lama": old, "baru": new,
                            "dunia": engine_result(case, y) if phase.startswith("teradaptasi") else None}
                if phase == "teradaptasi_ubah":
                    info["pph_ubah"] = str(expected["dunia"])
                    if expected["dunia"] == new:
                        continue
                q = question(case, mention=phase == "sadar")
                for i in range(repeats):
                    r = PhaseRun(case["id"], phase, i + 1, q)
                    start = time.perf_counter()
                    try:
                        turn = make_agent().ask(q)
                        r.detik = round(time.perf_counter() - start, 1)
                        score(r, turn, expected, plan.events, y, issued,
                              case["klaim"] if phase == "sadar" else "")
                    except Exception as exc:  # noqa: BLE001
                        r.galat, r.hasil = f"{type(exc).__name__}: {exc}", "galat"
                    runs.append(r)
                    if progress:
                        progress(r)
        plans.append(info)
    partial = {c["id"] for c in cases if c.get("sebagian")}
    return {"kasus": plans, "run": [asdict(r) for r in runs],
            "ringkasan": summarize([r for r in runs if r.kasus not in partial]),
            "ringkasan_sebagian": summarize([r for r in runs if r.kasus in partial]),
            "token": {"masuk": sum(r.token_masuk for r in runs), "keluar": sum(r.token_keluar for r in runs),
                      "keluar_per_run": round(sum(r.token_keluar for r in runs) / len(runs), 1) if runs else 0},
            "tabel": "sendiri (umpan ke jawaban)" if own_tables is not None else "label"}


def summarize(runs: list[PhaseRun]) -> dict:
    out: dict[str, dict] = {}
    for p in PHASES:
        rs = [r for r in runs if r.fase == p]
        if not rs:
            continue
        counts: dict[str, int] = {}
        for r in rs:
            counts[r.hasil] = counts.get(r.hasil, 0) + 1
        out[p] = {"n": len(rs), "hasil": counts, "melapor": sum(r.melapor for r in rs),
                  "sebut_peristiwa": sum(r.sebut_peristiwa for r in rs),
                  "anakronis": sum(bool(r.anakronis) for r in rs),
                  "detik_median": sorted(r.detik for r in rs)[len(rs) // 2],
                  "putaran_median": sorted(r.putaran for r in rs)[len(rs) // 2]}
    return out


def _cell(rs: list[dict]) -> str:
    counts: dict[str, int] = {}
    for r in rs:
        counts[r["hasil"]] = counts.get(r["hasil"], 0) + 1
    return ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "-"


def markdown_report(h: dict, meta: dict) -> str:
    lines = [
        "# Backtest temporal tingkat agent",
        "",
        f"Model: {meta.get('model')} ({meta.get('provider')}), {meta.get('waktu')}, ulangan {meta.get('ulang')}.",
        "",
        f"Tabel: {h.get('tabel', 'label')}" + (f" ({meta['tabel_sendiri']})" if meta.get("tabel_sendiri") else "") + ".",
        "",
        "Dunia beku: tabel tarif, regulasi.yaml (tanpa ringkasan), provenans (kosong), graf (peraturan yang terbit "
        "pada/sesudah tanggal potong disembunyikan; FAQ mati). Tidak beku: kode, prompt, dan dasar_hukum bawaan mesin.",
        "",
        "## Kasus",
        "",
        "| Kasus | Peristiwa | Beku | Jeda ke 1 Jan (hari) | Patch | Kunci ditinjau | PPh lama | PPh baru | PPh x1,2 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for k in h["kasus"]:
        lines.append(f"| {k['kasus']} | {', '.join(k['peristiwa'])} | {k['beku']} | {k['jeda_hari']} | "
                     f"{k['sumber_patch']} | {k['kunci_ditinjau']} | {k['pph_lama'] or '-'} | {k['pph_baru'] or '-'} | "
                     f"{k.get('pph_ubah') or '-'} |")
    lines += ["", "## Hasil per fase", "", "| Kasus | " + " | ".join(PHASES) + " |",
              "|---" * (len(PHASES) + 1) + "|"]
    for k in h["kasus"]:
        cells = [_cell([r for r in h["run"] if r["kasus"] == k["kasus"] and r["fase"] == p]) for p in PHASES]
        lines.append(f"| {k['kasus']} | " + " | ".join(cells) + " |")
    for title, key in (("Ringkasan (kasus lima fase)", "ringkasan"),
                       ("Ringkasan kasus sebagian (hanya fase teradaptasi)", "ringkasan_sebagian")):
        if not h.get(key):
            continue
        lines += ["", f"## {title}", "", "| Fase | n | Hasil | Melapor | Sebut peristiwa | Sitasi anakronis | "
                  "Detik (median) | Putaran (median) |", "|---|---|---|---|---|---|---|---|"]
        for p, s in h[key].items():
            hasil = ", ".join(f"{k} {v}" for k, v in sorted(s["hasil"].items()))
            lines.append(f"| {p} | {s['n']} | {hasil} | {s['melapor']} | {s['sebut_peristiwa']} | {s['anakronis']} | "
                         f"{s['detik_median']} | {s['putaran_median']} |")
    if h.get("token"):
        t = h["token"]
        lines += ["", f"Token LLM masuk / keluar: {t['masuk']} / {t['keluar']} ({t['keluar_per_run']} keluar per run)."]
    lines += ["", "Label hasil: `melapor` (report_possibly_stale tercatat, tanpa angka), `melapor_dengan_angka`, "
              "`angka_lama_diam` (menghitung dengan nilai lama tanpa melapor), `angka_lama_dengan_catatan` (sama, tetapi "
              "menyebut klaim pengguna), `angka_baru_tanpa_lapor` (angka dari "
              "ingatan atau nilai pengguna), `benar`, `ingatan` (varian x1,2 dijawab dengan nilai asli), "
              "`melapor_keliru`, `salah`, `tanpa_angka`, `galat`."]
    return "\n".join(lines) + "\n"


def write(h: dict, meta: dict, out_dir: Path, name: str = "backtest_agent") -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    md, js = out_dir / f"{name}.md", out_dir / f"{name}.json"
    md.write_text(markdown_report(h, meta), encoding="utf-8")
    js.write_text(json.dumps({"meta": meta, **h}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return md, js
