from __future__ import annotations

import copy
import datetime as _dt
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import yaml

from ..corpus.text_source import CorpusIndex, SourceText
from ..taxes import get as tax_module
from .assemble import IN_SCOPE, assemble_draft
from .evaluation import (
    BASE_YEAR,
    DRAFT_YEAR,
    Case,
    Pair,
    Score,
    Value,
    _key,
    _number_kind,
    _pair,
    _score_case,
    agrees,
    is_table_leaf,
    load_labels,
    mutate_text,
    new_value,
    path_steps,
)
from .gates import Effective, GateContext, effective_from_text, effective_year
from .llm import combine_llm, finding_leaves, groups_in_text, leaves

DATA_DIR = tax_module().data_dir
EVENTS_FILE = DATA_DIR / "peristiwa_backtest.yaml"


def load_events(path: Path | None = None) -> dict:
    data = yaml.safe_load(Path(path or EVENTS_FILE).read_text(encoding="utf-8"))
    for e in data["peristiwa"]:
        if e.get("nilai"):
            e["nilai"] = {k: (None if v is None else Decimal(str(v))) for k, v in e["nilai"].items()}
    return data


def documents(events: dict, labels: dict[str, dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}

    def add(name: str, date, role: str, event: dict | None = None) -> None:
        label = labels.get(name, {})
        values = (event or {}).get("nilai") or label.get("nilai") or {}
        number = (event or {}).get("nomor") or label.get("nomor")
        if number is None:
            raise ValueError(f"{name}: nomor tidak ada di draf_label.yaml maupun peristiwa_backtest.yaml")
        out[name] = {"tanggal": _date(date), "nomor": number, "dataset_tanggal": label.get("tanggal"),
                     "nilai": values, "peran": role, "peristiwa": event}

    for x in events.get("awal", []):
        add(x["peraturan"], x["tanggal"], "awal")
    for e in events["peristiwa"]:
        add(e["peraturan"], e["tanggal"], "peristiwa", e)
    for role in ("tanpa_perubahan", "kontrol_negatif"):
        for x in events.get(role, []):
            add(x["peraturan"], x["tanggal"], role)
    return out


def _date(x) -> _dt.date:
    return x if isinstance(x, _dt.date) else _dt.date.fromisoformat(str(x))


def _apply(raw: dict, values: Value) -> None:
    lengths: dict[tuple, int] = {}
    for j in values:
        steps = path_steps(j)
        for n, s in enumerate(steps):
            if isinstance(s, int):
                parent = tuple(steps[:n])
                lengths[parent] = max(lengths.get(parent, 0), s + 1)
    for parent, n in sorted(lengths.items(), key=lambda x: len(x[0])):
        node = raw
        for s in parent[:-1]:
            node = node.setdefault(s, [] if isinstance(s, int) else {}) if isinstance(node, dict) else node[s]
        if isinstance(node, dict):
            node[parent[-1]] = [dict(x) for x in (node.get(parent[-1]) or [])[:n]]
    for j, v in values.items():
        _pair(raw, j, v)


def stale_table(docs: dict[str, dict], before: _dt.date, roles: set[str] | None = None) -> dict:
    raw = copy.deepcopy(tax_module().load_raw(BASE_YEAR))
    for path in {j for info in docs.values() for j in info["nilai"]}:
        steps = path_steps(path)
        key, sub = steps[0], steps[1] if len(steps) > 1 else None
        if key not in IN_SCOPE:
            continue
        if isinstance(raw.get(key), dict) and isinstance(sub, str):
            if isinstance(raw[key].get(sub), list):
                raw[key][sub] = []
            else:
                raw[key].pop(sub, None)
        else:
            raw.pop(key, None)
    for _, info in sorted(docs.items(), key=lambda x: x[1]["tanggal"]):
        if info["tanggal"] < before and info["nilai"] and (roles is None or info["peran"] in roles):
            _apply(raw, info["nilai"])
    return raw


def source_texts(docs: dict[str, dict], dataset: Path, corpus: CorpusIndex | None = None) -> tuple[dict[str, SourceText],
                                                                                                dict[str, str]]:
    data = json.loads(Path(dataset).read_text(encoding="utf-8"))
    by_number: dict[str, list[dict]] = {}
    for d in data:
        by_number.setdefault((d.get("number") or "").strip(), []).append(d)
    corpus = corpus if corpus is not None else CorpusIndex()
    found, title = {}, {}
    for name, info in docs.items():
        candidates = [d for d in by_number.get(info["nomor"], []) if (d.get("full_text") or "").strip()]
        if info.get("dataset_tanggal"):
            candidates = [d for d in candidates if d.get("date") == info["dataset_tanggal"]] or candidates
        best = max(candidates, key=lambda d: len(d["full_text"]), default=None)
        title[name] = (best.get("title") if best is not None else None) or name
        t = corpus.pick(name, best["full_text"] if best is not None else None)
        if t is not None:
            found[name] = t
    return found, title


def _shifted(e: Effective, offset: int) -> Effective:
    def move(s: str) -> str:
        return re.sub(r"(?<!\d)((?:19|20)\d{2})(?!\d)", lambda m: str(int(m.group(1)) + offset), s)

    return Effective(e.source, move(e.start) if e.start else None, [move(p) for p in e.applies_to], e.retroactive,
                     e.transitional)


@dataclass
class Run:
    dokumen: str
    peran: str
    varian: str
    tanggal: str
    harapan: str = ""
    keputusan: str = ""
    sesuai_harapan: bool | None = None
    benar_siap: bool = False
    salah_lolos: bool = False
    draf_salah: bool = False
    llm_salah: bool = False
    penahan_tunggal: str = ""
    menahan: list[str] = field(default_factory=list)
    alasan: list[str] = field(default_factory=list)
    berlaku_terbaca: int | None = None
    berlaku_label: int | None = None
    lama_tidak_diketahui: list[str] = field(default_factory=list)
    det: dict = field(default_factory=dict)
    llm: dict = field(default_factory=dict)
    mutasi: dict = field(default_factory=dict)
    memori: dict = field(default_factory=dict)
    catatan: str = ""


def _s(v):
    return None if v is None else str(v)


def run_document(name: str, info: dict, text: str, stale: dict, pair: Pair, variant: str = "asli",
                 status: list[tuple[str, str]] | None = None, accepted: dict | None = None,
                 phase1_keys: list[str] | None = None, table=None) -> Run:
    event = info.get("peristiwa") or {}
    truth: Value = dict(info["nilai"])
    old_leaves = {j: v for key in {_key(x) for x in truth} for j, v in leaves(stale.get(key), key).items()}
    changed = {j: v for j, v in truth.items() if j not in old_leaves or old_leaves[j] != v}
    r = Run(name, info["peran"], variant, info["tanggal"].isoformat(), harapan=event.get("harapan", ""),
            berlaku_label=event.get("berlaku"))
    r.lama_tidak_diketahui = sorted({_key(j) for j in truth if stale.get(_key(j)) is None or (
        isinstance(stale[_key(j)], dict) and j.split(".", 1)[1] not in stale[_key(j)])})

    mutated_leaves: dict[str, Decimal] = {}
    if variant == "ubah":
        text_truth = {j: x for j, x in truth.items() if not is_table_leaf(j)}
        for v in sorted({v for j, v in changed.items() if v is not None and not is_table_leaf(j)}):
            paths = [j for j, x in text_truth.items() if x == v]
            kind = _number_kind(paths[0])
            if any(_number_kind(j) != kind for j in paths):
                continue
            new = new_value(v, kind, False)
            mutated, matched = mutate_text(text, v, new, kind, "konsisten")
            if matched:
                text = mutated
                mutated_leaves.update(dict.fromkeys(paths, new))
        if not mutated_leaves:
            r.keputusan, r.catatan = "dilewati", "tidak ada angka berubah dengan terbilang yang bisa dimutasi"
            return r
        truth.update(mutated_leaves)
        r.mutasi = {j: _s(v) for j, v in mutated_leaves.items()}

    results, checker = pair.extract(text, groups_in_text(text))
    if table is not None and table.extraction is not None:
        results = [*results, table.extraction]
        checker = combine_llm(checker, table.llm)
    det = finding_leaves(results)
    r.det = {j: _s(v) for j, v in det.items()}
    if checker is not None:
        r.llm = {j: _s(v) for j, v in checker.values.items()}
    for j, v in mutated_leaves.items():
        got = checker.values.get(j) if checker is not None else None
        r.memori[j] = ("tidak_ada" if got is None else "dibaca" if got == v
                       else "ingatan" if got == info["nilai"].get(j) else "lain")

    real = effective_from_text(text, "s")
    th, _ = effective_year(real)
    r.berlaku_terbaca = None if real.transitional else th
    target = event.get("berlaku") or info["tanggal"].year
    effective = _shifted(real, DRAFT_YEAR - target)
    keys = event.get("kunci_fase1") or sorted({_key(j) for j in truth})
    if info["peran"] == "kontrol_negatif":
        keys = []
    if phase1_keys is not None:
        keys = list(phase1_keys)
        r.catatan = f"kunci Fase 1 dari analisis dampak: {', '.join(keys) or '-'}"
    ctx = GateContext(phase1_keys=keys, in_force={"s": effective}, llm=checker, source_status=None if status is None
                      else {"s": status})
    expected = copy.deepcopy(stale)
    _apply(expected, truth)
    case = Case(name, info["peran"], variant)
    try:
        d = assemble_draft(DRAFT_YEAR, results, BASE_YEAR, ctx, base=stale)
        _score_case(case, d, expected, checker)
        r.alasan = [x for g in d.gates if g.passed is False for x in g.reasons]
        if d.decision == "siap" and not case.salah_lolos:
            r.benar_siap = any(_key(j) in {p.key for p in d.berubah} for j in changed) or not changed
        if d.decision == "siap" and accepted is not None:
            accepted.update({p.key: copy.deepcopy(p.new) for p in d.berubah})
    except (ValueError, KeyError) as e:
        case.keputusan, case.catatan = "ditolak", str(e)
    r.keputusan, r.salah_lolos, r.menahan = case.keputusan, case.salah_lolos, case.menahan
    r.draf_salah, r.llm_salah, r.penahan_tunggal = case.draf_salah, case.llm_salah, case.penahan_tunggal
    r.catatan = r.catatan or case.catatan
    if r.harapan == "siap":
        r.sesuai_harapan = r.benar_siap
    elif r.harapan == "tahan" or info["peran"] == "kontrol_negatif":
        r.sesuai_harapan = r.keputusan != "siap"
    elif info["peran"] == "tanpa_perubahan":
        r.sesuai_harapan = not r.salah_lolos
    return r


def detect(docs: dict[str, dict], title: dict[str, str], text: dict[str, str], classifier=None) -> dict[str, dict]:
    from ..monitor.classify import classify, load_watchlist
    from ..monitor.classify_llm import keyword_excerpt
    from ..monitor.evaluation import without_self
    from ..monitor.identity import canon_id

    wl = load_watchlist()
    out = {}
    for name, info in docs.items():
        if info["peran"] == "awal":
            continue
        ident = canon_id(info["nomor"]) or canon_id(name)
        t = title.get(name, name)
        rules = classify(t, "", ident, without_self(wl, ident)).category
        llm = None
        if classifier is not None and name in text:
            llm = classifier.classify(name, t, "", keyword_excerpt(text[name])).category
        out[name] = {"aturan": rules, "llm": llm,
                     "masuk_antrean": rules != "tidak_relevan" or (llm is not None and llm != "tidak_relevan")}
    return out


def _tables(found: dict[str, SourceText], read_table) -> dict:
    from .ter_table import has_ter_table

    if read_table is None:
        return {}
    out = {}
    for name, t in found.items():
        if has_ter_table(t.text):
            r = read_table(t, t.text)
            if r is not None:
                out[name] = r
    return out


def phase2_texts(found: dict[str, SourceText], text: dict[str, str], enabled: bool, progress=None) -> dict[str, str]:
    if not enabled:
        return text
    from .body_tables import reflow_source

    out = dict(text)
    for name, t in found.items():
        r = reflow_source(t)
        out[name] = r.text
        if progress:
            for line in r.lines:
                progress(f"{name}: {line}")
    return out


def pdf_table_reader(vision=None, progress=None):
    from .ter_table import read_table

    def reader(source: SourceText, text: str):
        pdf = source.pdf()
        if pdf is None:
            if progress:
                progress(f"tabel lampiran tidak dibaca: PDF JDIH lokal tidak ada ({source.pdf_url() or '-'})")
            return None
        h = read_table(pdf.read_bytes(), pdf.name, vision)
        if progress:
            for line in h.lines:
                progress(line)
        return h

    return reader


def backtest(dataset: Path, client=None, status_for=None, variants: tuple[str, ...] = ("asli", "ubah"),
             classifier=None, progress=None, events_file: Path | None = None, phase1_for=None,
             read_table=None, body_tables: bool = False, note=None) -> dict:
    labels = load_labels()
    docs = documents(load_events(events_file), labels)
    found, title = source_texts(docs, dataset)
    text, source = {n: t.text for n, t in found.items()}, {n: t.label for n, t in found.items()}
    tables = _tables(found, read_table)
    p2 = phase2_texts(found, text, body_tables, note)
    pair = client if isinstance(client, Pair) else Pair("pola+llm", client)
    runs: list[Run] = []
    scores = {v: {"det": Score(), "llm": Score(), "sepakat": Score(), "tabel_ocr": Score(), "tabel_visi": Score()}
              for v in variants}
    targets = [n for n, i in docs.items() if i["peran"] != "awal"]
    detection = detect(docs, title, text, classifier) if phase1_for else None
    for n, name in enumerate(targets, 1):
        info = docs[name]
        if name not in text:
            runs.append(Run(name, info["peran"], "asli", info["tanggal"].isoformat(), keputusan="dilewati",
                            catatan="teks tidak ditemukan"))
            continue
        if detection is not None and not detection[name]["masuk_antrean"]:
            r = Run(name, info["peran"], "asli", info["tanggal"].isoformat(), keputusan="tidak_terdeteksi",
                    harapan=(info.get("peristiwa") or {}).get("harapan", ""))
            r.sesuai_harapan = r.harapan != "siap"
            runs.append(r)
            continue
        keys = phase1_for(name, info["nomor"], title.get(name, name), text[name]) if phase1_for else None
        stale = stale_table(docs, info["tanggal"])
        status = status_for(name, info["nomor"], info["tanggal"].year) if status_for else None
        for v in variants:
            if v == "ubah" and info["peran"] != "peristiwa":
                continue
            r = run_document(name, info, p2[name], stale, pair, v, status, phase1_keys=keys, table=tables.get(name))
            runs.append(r)
            if info["peran"] == "peristiwa" and r.keputusan != "dilewati":
                truth = dict(info["nilai"])
                if v == "ubah":
                    truth.update({j: Decimal(x) for j, x in r.mutasi.items()})
                table_truth = {j: x for j, x in truth.items() if is_table_leaf(j)}
                truth = {j: x for j, x in truth.items() if not is_table_leaf(j)}
                det_all = {j: Decimal(x) if x is not None else None for j, x in r.det.items()}
                det = {j: x for j, x in det_all.items() if not is_table_leaf(j)}
                scores[v]["det"].add(truth, det, name)
                if pair.client is not None:
                    llm_all = {j: Decimal(x) if x is not None else None for j, x in r.llm.items()}
                    llm = {j: x for j, x in llm_all.items() if not is_table_leaf(j)}
                    scores[v]["llm"].add(truth, llm, name)
                    scores[v]["sepakat"].add(truth, agrees(det, llm), name)
                tr = tables.get(name)
                if table_truth and tr is not None:
                    scores[v]["tabel_ocr"].add(table_truth, {j: x for j, x in det_all.items() if is_table_leaf(j)},
                                               name)
                    if tr.llm is not None:
                        scores[v]["tabel_visi"].add(table_truth, tr.llm.values, name)
        if progress:
            progress(n, len(targets), name)
    return {
        "dokumen": {n: {"tanggal": i["tanggal"].isoformat(), "peran": i["peran"], "sumber_teks": source.get(n)}
                    for n, i in docs.items()},
        "deteksi": detection if detection is not None else detect(docs, title, text, classifier),
        "run": [r.__dict__ for r in runs],
        "skor": {v: {k: s.summary() for k, s in x.items()} for v, x in scores.items()},
        "rincian_salah": {v: {k: s.wrong for k, s in x.items()} for v, x in scores.items()},
        "llm": pair.client is not None,
    }


def table_gaps(own: dict, truth: dict) -> list[str]:
    out = []
    for key in IN_SCOPE:
        mine, real = leaves(own.get(key), key), leaves(truth.get(key), key)
        out += sorted(j for j in set(mine) | set(real) if mine.get(j) != real.get(j))
    return out


def cumulative(dataset: Path, client=None, status_for=None, progress=None, events_file: Path | None = None,
               classifier=None, phase1_for=None, read_table=None, body_tables: bool = False, note=None) -> dict:
    labels = load_labels()
    docs = documents(load_events(events_file), labels)
    found, title = source_texts(docs, dataset)
    text, source = {n: t.text for n, t in found.items()}, {n: t.label for n, t in found.items()}
    tables = _tables(found, read_table)
    p2 = phase2_texts(found, text, body_tables, note)
    detection = detect(docs, title, text, classifier) if phase1_for else None
    snapshots = [{"tanggal": None, "dokumen": None, "tabel": _plain_table(own_start := stale_table(
        docs, _dt.date.max, roles={"awal"}))}]
    pair = client if isinstance(client, Pair) else Pair("pola+llm", client)
    own = copy.deepcopy(own_start)
    runs, steps = [], []
    targets = sorted((n for n, i in docs.items() if i["peran"] != "awal"), key=lambda n: docs[n]["tanggal"])
    for n, name in enumerate(targets, 1):
        info = docs[name]
        truth_before = stale_table(docs, info["tanggal"])
        gaps_before = table_gaps(own, truth_before)
        if name not in text:
            runs.append(Run(name, info["peran"], "asli", info["tanggal"].isoformat(), keputusan="dilewati",
                            catatan="teks tidak ditemukan"))
            continue
        if detection is not None and not detection[name]["masuk_antrean"]:
            r = Run(name, info["peran"], "asli", info["tanggal"].isoformat(), keputusan="tidak_terdeteksi",
                    harapan=(info.get("peristiwa") or {}).get("harapan", ""))
            runs.append(r)
            steps.append({"dokumen": name, "tanggal": info["tanggal"].isoformat(), "peran": info["peran"],
                          "keputusan": r.keputusan, "diterapkan": [], "selisih_sebelum": len(gaps_before),
                          "selisih_sesudah": table_gaps(own, stale_table(docs, info["tanggal"] + _dt.timedelta(days=1)))})
            continue
        status = status_for(name, info["nomor"], info["tanggal"].year) if status_for else None
        keys = phase1_for(name, info["nomor"], title.get(name, name), text[name]) if phase1_for else None
        accepted: dict = {}
        r = run_document(name, info, p2[name], copy.deepcopy(own), pair, "asli", status, accepted,
                         phase1_keys=keys, table=tables.get(name))
        runs.append(r)
        for key, value in accepted.items():
            own[key] = value
        after = stale_table(docs, info["tanggal"] + _dt.timedelta(days=1))
        steps.append({"dokumen": name, "tanggal": info["tanggal"].isoformat(), "peran": info["peran"],
                      "keputusan": r.keputusan, "diterapkan": sorted(accepted),
                      "selisih_sebelum": len(gaps_before), "selisih_sesudah": table_gaps(own, after)})
        if accepted:
            snapshots.append({"tanggal": info["tanggal"].isoformat(), "dokumen": name, "tabel": _plain_table(own)})
        if progress:
            progress(n, len(targets), name)
    final = stale_table(docs, _dt.date.max)
    return {
        "dokumen": {n: {"tanggal": i["tanggal"].isoformat(), "peran": i["peran"], "sumber_teks": source.get(n)}
                    for n, i in docs.items()},
        "run": [r.__dict__ for r in runs],
        "langkah": steps,
        "selisih_akhir": table_gaps(own, final),
        "llm": pair.client is not None,
        "deteksi": detection,
        "fase1": "analisis dampak" if phase1_for else "label (oracle)",
        "tabel_sendiri": snapshots,
    }


def _plain_table(raw: dict) -> dict:
    def plain(x):
        if isinstance(x, dict):
            return {k: plain(v) for k, v in x.items()}
        if isinstance(x, list):
            return [plain(v) for v in x]
        if isinstance(x, Decimal):
            return int(x) if x == x.to_integral_value() else float(x)
        return x

    return plain(copy.deepcopy(raw))


def cumulative_report(h: dict, meta: dict) -> str:
    b = ["# Replay kumulatif tanpa manusia", "",
         f"Dibuat oleh `pph21 draft-backtest --cumulative`. Model LLM: {meta.get('model', '-')}. Tabel pembanding tiap "
         "langkah adalah keluaran sistem sendiri di langkah sebelumnya (draf `siap` diterapkan, draf `tahan` tidak); "
         "selisih = daun nilai yang berbeda dari riwayat berlabel.", "",
         "| dokumen | tanggal | peran | keputusan | key diterapkan | selisih sebelum | selisih sesudah |",
         "|---|---|---|---|---|---|---|"]
    for s in h["langkah"]:
        b.append(f"| {s['dokumen']} | {s['tanggal']} | {s['peran']} | {s['keputusan']} | "
                 f"{', '.join(s['diterapkan']) or '-'} | {s['selisih_sebelum']} | {len(s['selisih_sesudah'])} |")
    wrong = sum(r["salah_lolos"] for r in h["run"])
    b += ["", f"- Salah lolos: **{wrong}**",
          f"- Selisih akhir terhadap riwayat berlabel: **{len(h['selisih_akhir'])}** daun"
          + (f" ({', '.join(h['selisih_akhir'][:12])}{' ...' if len(h['selisih_akhir']) > 12 else ''})"
             if h["selisih_akhir"] else "")]
    return "\n".join(b) + "\n"


def _pct(x) -> str:
    return "-" if x is None else f"{x * 100:.1f}%"


def markdown_report(h: dict, meta: dict) -> str:
    runs = h["run"]
    b = ["# Backtest temporal: sistem dibekukan sebelum setiap perubahan nyata", "",
         f"Dibuat oleh `pph21 draft-backtest`. Model LLM: {meta.get('model', '-')}, prompt {meta.get('prompt', '-')}. "
         "Peristiwa: `taxagent/taxes/pph21/data/peristiwa_backtest.yaml`; label nilai: `draf_label.yaml`.", "",
         "## 1. Per peristiwa", "",
         "| peristiwa | tanggal | terdeteksi | varian | harapan | keputusan | sesuai | salah lolos | gerbang menahan | "
         "berlaku terbaca/label | nilai lama tidak diketahui |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    det = h["deteksi"]
    for r in runs:
        if r["peran"] != "peristiwa":
            continue
        d = det.get(r["dokumen"], {})
        flag = "ya" if d.get("masuk_antrean") else "**tidak**"
        b.append(f"| {r['dokumen']} | {r['tanggal']} | {flag} | {r['varian']} | {r['harapan']} | {r['keputusan']} | "
                 f"{'ya' if r['sesuai_harapan'] else '**tidak**' if r['sesuai_harapan'] is False else '-'} | "
                 f"{'**ya**' if r['salah_lolos'] else '0'} | {', '.join(r['menahan']) or '-'} | "
                 f"{r['berlaku_terbaca']}/{r['berlaku_label']} | {', '.join(r['lama_tidak_diketahui']) or '-'} |")
    b += ["", "## 2. Ringkasan", ""]
    for v in ("asli", "ubah"):
        rs = [r for r in runs if r["peran"] == "peristiwa" and r["varian"] == v and r["keputusan"] != "dilewati"]
        if not rs:
            continue
        c = Counter(r["keputusan"] for r in rs)
        b.append(f"- **{v}**: {len(rs)} peristiwa; siap {c.get('siap', 0)} (benar {sum(r['benar_siap'] for r in rs)}), "
                 f"tahan {c.get('tahan', 0)}, tidak ada perubahan {c.get('tidak_ada_perubahan', 0)}, "
                 f"ditolak {c.get('ditolak', 0)}; sesuai harapan {sum(bool(r['sesuai_harapan']) for r in rs)}/{len(rs)}; "
                 f"**salah lolos {sum(r['salah_lolos'] for r in rs)}**")
    mem = Counter(x for r in runs if r["varian"] == "ubah" for x in r["memori"].values())
    if mem:
        b.append(f"- LLM pada angka yang dimutasi: dibaca {mem.get('dibaca', 0)}, **dari ingatan {mem.get('ingatan', 0)}**, "
                 f"lain {mem.get('lain', 0)}, tidak menjawab {mem.get('tidak_ada', 0)}")
    for role, title in (("tanpa_perubahan", "Dokumen yang menulis ulang nilai lama"),
                        ("kontrol_negatif", "Kontrol negatif")):
        rs = [r for r in runs if r["peran"] == role]
        if rs:
            b.append(f"- {title}: {len(rs)} dokumen; siap {sum(r['keputusan'] == 'siap' for r in rs)}, "
                     f"salah lolos **{sum(r['salah_lolos'] for r in rs)}**; keputusan "
                     + ", ".join(f"{k} {n}" for k, n in Counter(r['keputusan'] for r in rs).items()))
    scored = [r for r in runs if r["keputusan"] not in ("dilewati", "ditolak")]
    if scored:
        b.append(f"- Pembanding pada {len(scored)} run (tanpa panggilan LLM tambahan): nilai salah masuk tabel bila "
                 f"draf diterima tanpa gerbang **{sum(r.get('draf_salah', False) for r in scored)}**, bila bacaan LLM "
                 f"diterima langsung **{sum(r.get('llm_salah', False) for r in scored)}**, dengan G1-G8 "
                 f"**{sum(r['salah_lolos'] for r in scored)}**")
    flagged = [n for n, d in det.items() if h["dokumen"][n]["peran"] == "peristiwa" and d["masuk_antrean"]]
    total = sum(1 for n in det if h["dokumen"][n]["peran"] == "peristiwa")
    b.append(f"- Deteksi pemantau (aturan judul ATAU LLM cuplikan kata kunci): {len(flagged)}/{total} peristiwa")
    c = Counter(d.get("sumber_teks") or "tidak ada" for d in h["dokumen"].values())
    b.append("- Sumber teks (urutan sistem terpasang: JDIH andal, pajak.go.id, JDIH perlu_dicek): "
             + ", ".join(f"{k} {n}" for k, n in sorted(c.items())))
    if meta.get("tabel_lampiran"):
        b.append(f"- Tabel lampiran: {meta['tabel_lampiran']}; dinilai terpisah (`tabel_ocr`, `tabel_visi`), "
                 "ekstraktor teks dinilai tanpa daun tabel")
    b += ["", "## 3. Ekstraksi per angka (peristiwa)", "", "| varian | ekstraktor | benar | salah | terlewat | presisi | recall |",
          "|---|---|---|---|---|---|---|"]
    for v, x in h["skor"].items():
        for e, s in x.items():
            empty = s["benar"] + s["salah"] + s["terlewat"] == 0
            if e != "det" and ((not h["llm"] and e not in ("tabel_ocr", "tabel_visi")) or (empty and e.startswith("tabel"))):
                continue
            b.append(f"| {v} | {e} | {s['benar']} | {s['salah']} | {s['terlewat']} | {_pct(s['presisi'])} | {_pct(s['recall'])} |")
    wrong = [r for r in runs if r["salah_lolos"] or r["sesuai_harapan"] is False]
    if wrong:
        b += ["", "## 4. Kasus yang perlu dibaca", ""]
        for r in wrong:
            b.append(f"- {r['dokumen']} ({r['varian']}): {r['keputusan']}; {r['catatan'] or '; '.join(r['alasan'][:3])}")
    return "\n".join(b) + "\n"
