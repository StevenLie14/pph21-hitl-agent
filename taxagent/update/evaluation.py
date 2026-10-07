from __future__ import annotations

import copy
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import yaml

from ..taxes import get as tax_module
from .amounts import format_rupiah, to_terbilang, yaml_number
from .assemble import Draft, assemble_draft
from .extraction import extract_amounts
from .gates import Effective, GateContext, effective_from_text, effective_year
from .llm import GROUPS, combine_llm, extract_llm, finding_leaves, groups_in_text, leaves, reread_changed

DATA_DIR = tax_module().data_dir

LABELS_FILE = DATA_DIR / "draf_label.yaml"
DRAFT_YEAR, BASE_YEAR = 2027, 2024
MUTATION_KINDS = ("asli", "ubah", "digit", "kata", "kali10", "tengah")

Value = dict[str, Decimal | None]


TABLE_KEYS = ("ter_bulanan", "ter_harian.lapisan")


def is_table_leaf(path: str) -> bool:
    return any(path == k or path.startswith(k + ".") or path.startswith(k + "[") for k in TABLE_KEYS)


def table_label(spec: dict) -> Value:
    raw = tax_module().load_raw(int(spec["tahun"]))
    out: Value = {}
    for k in spec["kunci"]:
        node = raw
        for s in path_steps(k):
            node = node[s]
        out.update(leaves(node, k))
    return out


def load_labels(path: Path | None = None) -> dict[str, dict]:
    data = yaml.safe_load(Path(path or LABELS_FILE).read_text(encoding="utf-8"))["dokumen"]
    for info in data.values():
        info["nilai"] = {k: (None if v is None else Decimal(str(v))) for k, v in (info.get("nilai") or {}).items()}
        if info.get("nilai_dari_tarif"):
            info["nilai"].update(table_label(info["nilai_dari_tarif"]))
    return data


def load_text_labels(path: Path | None = None) -> dict[str, dict]:
    data = load_labels(path)
    for info in data.values():
        info["nilai"] = {k: v for k, v in info["nilai"].items() if not is_table_leaf(k)}
    return data


def texts_from_dataset(label: dict[str, dict], path: Path) -> dict[str, str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    results = {}
    for i, info in label.items():
        candidates = [d for d in data if (d.get("number") or "").strip() == info["nomor"] and (d.get("full_text") or "").strip()]
        if info.get("tanggal"):
            candidates = [d for d in candidates if d.get("date") == info["tanggal"]] or candidates
        if candidates:
            results[i] = max(candidates, key=lambda d: len(d["full_text"]))["full_text"]
    return results


def _text_only(values: Value) -> Value:
    return {j: v for j, v in values.items() if not is_table_leaf(j)}


def label_groups(values: Value) -> list[str]:
    return sorted({_key(j) for j in values if _key(j) in GROUPS})


def _key(path: str) -> str:
    return path.split(".")[0].split("[")[0]


@dataclass
class Score:
    correct: int = 0
    wrong: list[str] = field(default_factory=list)
    missed: list[str] = field(default_factory=list)

    def add(self, label: Value, predicted: Value, doc: str) -> None:
        for j, v in predicted.items():
            if j in label and label[j] == v:
                self.correct += 1
            else:
                self.wrong.append(f"{doc}: {j}={v} (label {label.get(j, 'tidak ada')})")
        self.missed += [f"{doc}: {j}={v}" for j, v in label.items() if j not in predicted]

    @property
    def precision(self) -> float | None:
        n = self.correct + len(self.wrong)
        return self.correct / n if n else None

    @property
    def recall(self) -> float | None:
        n = self.correct + len(self.missed)
        return self.correct / n if n else None

    def summary(self) -> dict:
        return {"benar": self.correct, "salah": len(self.wrong), "terlewat": len(self.missed),
                "presisi": self.precision, "recall": self.recall}


def agrees(det: Value, llm: Value) -> Value:
    return {j: v for j, v in det.items() if j in llm and llm[j] == v}


def _number_kind(path: str) -> str:
    if path.endswith("maksimal_tanggungan"):
        return "orang"
    if "persen" in path or path.startswith("pph_final_honorarium_pns"):
        return "persen"
    return "rupiah"


def _word_pattern(d: Decimal) -> str:
    return r"\s+".join(re.escape(w) for w in to_terbilang(d).split())


def _fmt_percent(d: Decimal) -> str:
    s = format(d.normalize(), "f")
    return s.replace(".", ",")


def mutate_text(text: str, old: Decimal, new: Decimal, kind: str, mode: str) -> tuple[str, int]:
    t = re.sub(r"\s+", " ", text)
    old_words = _word_pattern(old)
    if kind == "rupiah":
        digit = r"\s?\.\s?".join(f"{int(old):,}".split(","))
        pattern = re.compile(rf"(?<![\d.])(RP\.?\s*)({digit})((?:\s?,\s?\d{{2}})?)(?:(\s*\(\s*\(?\s*)({old_words})(?=\s*(?:rupiah|\)|,)))?", re.I)
        new_digits = format_rupiah(new)[2:-3]
    elif kind == "persen":
        digit = r"\s?,\s?".join(re.escape(x) for x in _fmt_percent(old).split(","))
        pattern = re.compile(rf"(?<![\d,.])()({digit})(\s?%)(?:(\s*\(\s*)({old_words})(?=\s+persen))?", re.I)
        new_digits = _fmt_percent(new)
    else:
        pattern = re.compile(rf"(paling\s+banyak\s+)({int(old)})(\s*)(?:(\(\s*)({old_words})(?=\s*\)))?", re.I)
        new_digits = str(int(new))
    matched = 0

    def replace(m: re.Match) -> str:
        nonlocal matched
        has_words = m.group(5) is not None
        matched += has_words
        d = new_digits if mode in ("konsisten", "digit") else m.group(2)
        k = (to_terbilang(new) if mode in ("konsisten", "kata") else m.group(5)) if has_words else ""
        return f"{m.group(1)}{d}{m.group(3)}{(m.group(4) or '') + k if has_words else ''}"

    return pattern.sub(replace, t), matched


def new_value(v: Decimal, kind: str, times_ten: bool) -> Decimal | None:
    if times_ten:
        return v * 10 if v else None
    if kind == "rupiah":
        return (v * Decimal("1.2") / 1000).quantize(Decimal(1), ROUND_HALF_UP) * 1000
    if kind == "persen":
        return Decimal(1) if v == 0 else v + 1
    return v + 1


_RE_STEP = re.compile(r"\.?([A-Za-z_0-9/]+)|\[(\d+)\]")


def path_steps(path: str) -> list[str | int]:
    return [m.group(1) if m.group(1) is not None else int(m.group(2)) for m in _RE_STEP.finditer(path)]


def _pair(raw: dict, path: str, value: Decimal | None) -> None:
    steps = path_steps(path)
    v = None if value is None else yaml_number(value)
    node = raw
    for step, nxt in zip(steps, steps[1:]):
        empty = [] if isinstance(nxt, int) else {}
        if isinstance(step, int):
            while len(node) <= step:
                node.append({"batas_atas": None, "persen": 0})
            if not isinstance(node[step], (dict, list)):
                node[step] = empty
            node[step] = dict(node[step]) if isinstance(node[step], dict) else node[step]
            node = node[step]
        else:
            if not isinstance(node.get(step), (dict, list)):
                node[step] = empty
            node = node[step]
    last = steps[-1]
    if isinstance(last, int):
        while len(node) <= last:
            node.append(None)
    node[last] = v


def base_with(values: Value) -> dict:
    raw = copy.deepcopy(tax_module().load_raw(BASE_YEAR))
    lengths: dict[str, int] = {}
    for j in values:
        m = re.fullmatch(r"([a-z_0-9]+)\[(\d+)\]\..+", j)
        if m:
            lengths[m.group(1)] = max(lengths.get(m.group(1), 0), int(m.group(2)) + 1)
    for key, n in lengths.items():
        raw[key] = [dict(x) for x in raw[key][:n]]
    for j, v in values.items():
        _pair(raw, j, v)
    return raw


@dataclass
class Case:
    dokumen: str
    set: str
    jenis: str
    angka: str = ""
    keputusan: str = ""
    salah_lolos: bool = False
    menahan: list[str] = field(default_factory=list)
    catatan: str = ""
    alasan_g4: list[str] = field(default_factory=list)
    draf_salah: bool = False
    llm_salah: bool = False
    penahan_tunggal: str = ""


@dataclass
class Pair:
    name: str = "pola+llm"
    client: object = None
    client2: object = None

    def graph_llm(self, text: str, groups: list[str]):
        from ..monitor.memory_graph import from_texts
        from ..tools import regulation_graph as G
        from .graph_updater import extract_with_graph

        G.use_client(from_texts({"DOK": {"teks": text}}))
        try:
            return extract_with_graph("DOK", text, self.client, groups)
        finally:
            G.use_client(None)

    def extract(self, text: str, groups: list[str], reuse=None):
        from .graph_updater import to_extraction_result
        from .llm import LLMResult

        if self.name == "pola+llm":
            if not self.client:
                return [extract_amounts(text, "s")], None
            if reuse is not None and reuse[0] is not None:
                return [extract_amounts(text, "s")], reread_changed(reuse[0], text, self.client, groups, reuse[1])
            return [extract_amounts(text, "s")], extract_llm(text, self.client, groups)
        primary = to_extraction_result(self.graph_llm(text, groups), text, "s")
        if self.name == "graf+pola":
            return [primary], LLMResult(values=finding_leaves([extract_amounts(text, "s")]))
        return [primary], extract_llm(text, self.client2, groups)


def _pairs(client) -> Pair:
    return client if isinstance(client, Pair) else Pair("pola+llm", client)


def _run(text: str, expected: Value, keys: list[str], effective: Effective, client, groups: list[str],
              status: list[tuple[str, str]] | None = None, table=None, reuse=None):
    results, checker = _pairs(client).extract(text, groups, reuse)
    text_reading = checker
    if table is not None and table.extraction is not None:
        results = [*results, table.extraction]
        checker = combine_llm(checker, table.llm)
    k = GateContext(phase1_keys=keys, in_force={"s": effective}, llm=checker,
                source_status=None if status is None else {"s": status})
    return assemble_draft(DRAFT_YEAR, results, BASE_YEAR, k, base=base_with(expected)), checker, text_reading


def _llm_wrong(llm, expected_base: dict) -> bool:
    if llm is None:
        return False
    expected: dict[str, Decimal | None] = {}
    for key in {_key(j) for j in llm.values}:
        if expected_base.get(key) is not None:
            leaves(expected_base[key], key, expected)
    return any(j in expected and v is not None and expected[j] is not None
               and Decimal(str(v)) != Decimal(str(expected[j])) for j, v in llm.values.items())


def _score_case(c: Case, d: Draft, expected_base: dict, llm=None) -> None:
    c.keputusan = d.decision
    c.menahan = [g.code for g in d.gates if g.passed is False]
    c.alasan_g4 = [r for g in d.gates if g.code == "G4" and g.passed is False for r in g.reasons]
    wrong = [p for p in d.berubah if leaves(p.new, p.key) != leaves(expected_base.get(p.key), p.key)]
    c.draf_salah = bool(wrong)
    c.llm_salah = _llm_wrong(llm, expected_base)
    if wrong and len(c.menahan) == 1:
        c.penahan_tunggal = c.menahan[0]
    if d.decision == "siap" and wrong:
        c.salah_lolos = True
        c.catatan = f"{wrong[0].key}: draf {wrong[0].new}, seharusnya {expected_base.get(wrong[0].key)}"


def mutation_cases(doc: str, info: dict, text: str, client, status: list[tuple[str, str]] | None = None,
                   table=None) -> list[Case]:
    label: Value = info["nilai"]
    groups = groups_in_text(text)
    clean = Effective("s", applies_to=[f"TAHUN PAJAK {DRAFT_YEAR}"])
    mid_year = Effective("s", applies_to=[f"MASA PAJAK JULI {DRAFT_YEAR}"])
    results = []

    c = Case(doc, info["set"], "asli")
    original = None
    try:
        d, checker, original = _run(text, label, sorted({_key(j) for j in label}), clean, client, groups, status,
                                    table)
        _score_case(c, d, base_with(label), checker)
    except ValueError as e:
        c.keputusan, c.catatan = "ditolak", str(e)
    results.append(c)

    text_label = {j: x for j, x in label.items() if not is_table_leaf(j)}
    for v in sorted({v for v in text_label.values() if v is not None}):
        paths = [j for j, x in text_label.items() if x == v]
        number_kind = _number_kind(paths[0])
        if any(_number_kind(j) != number_kind for j in paths):
            continue
        for kind in MUTATION_KINDS[1:]:
            new = new_value(v, number_kind, kind == "kali10")
            c = Case(doc, info["set"], kind, f"{','.join(paths)}: {v} -> {new}")
            if new is None:
                c.keputusan = "dilewati"
                results.append(c)
                continue
            mode = {"digit": "digit", "kata": "kata"}.get(kind, "konsisten")
            mutated, matched = mutate_text(text, v, new, number_kind, mode)
            if matched == 0:
                c.keputusan, c.catatan = "dilewati", "angka dengan terbilang tidak ditemukan di teks"
                results.append(c)
                continue
            expected = dict(label)
            if kind in ("ubah", "kali10", "tengah"):
                expected.update(dict.fromkeys(paths, new))
            keys = sorted({_key(j) for j in paths})
            try:
                d, checker, _ = _run(mutated, label, keys, mid_year if kind == "tengah" else clean, client, groups,
                                     status, table, reuse=(original, set(keys)))
                _score_case(c, d, base_with(expected), checker)
            except ValueError as e:
                c.keputusan, c.catatan = "ditolak", str(e)
            results.append(c)
    return results


def evaluate(label: dict[str, dict], text: dict[str, str], client=None, mutations: bool = True, workers: int = 4,
             progress=None, status: dict[str, list[tuple[str, str]] | None] | None = None,
             tables: dict | None = None) -> dict:
    tables = tables or {}
    replay: dict[str, dict] = {}
    pair = _pairs(client)
    scores = {s: {"det": Score(), "llm": Score(), "graf": Score(), "llm2": Score(), "sepakat": Score(),
                  "tabel_ocr": Score(), "tabel_visi": Score()} for s in ("dev", "uji")}
    g6 = {s: Counter() for s in ("dev", "uji")}
    g6_wrong: list[str] = []

    def one(i: str):
        info, t = label[i], text[i]
        det = finding_leaves([extract_amounts(t, i)])
        llm = extract_llm(t, pair.client) if pair.client is not None else None
        groups = groups_in_text(t)
        graph_result = pair.graph_llm(t, groups) if pair.name.startswith("graf") and pair.client is not None else None
        llm2 = extract_llm(t, pair.client2) if pair.client2 is not None else None
        b = effective_from_text(t, i)
        th, note = effective_year(b)
        if b.transitional:
            th, note = None, "ketentuan peralihan"
        cases = mutation_cases(i, info, t, pair, (status or {}).get(i), tables.get(i)) if mutations else []
        return i, det, llm, graph_result, llm2, th, note, cases

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        results = list(ex.map(one, [i for i in label if i in text]))
    all_cases: list[Case] = []
    for n, (i, det, llm, graph_result, llm2, th, note, cases) in enumerate(results, 1):
        info = label[i]
        s = scores[info["set"]]
        text_label = {j: v for j, v in info["nilai"].items() if not is_table_leaf(j)}
        table_label = {j: v for j, v in info["nilai"].items() if is_table_leaf(j)}
        det = _text_only(det)
        llm_values = _text_only(llm.values) if llm is not None else None
        s["det"].add(text_label, det, i)
        if llm is not None:
            s["llm"].add(text_label, llm_values, i)
        if graph_result is not None:
            s["graf"].add(text_label, _text_only(graph_result.values), i)
        if llm2 is not None:
            s["llm2"].add(text_label, _text_only(llm2.values), i)
        tr = tables.get(i)
        if table_label and tr is not None:
            s["tabel_ocr"].add(table_label, finding_leaves([tr.extraction]) if tr.extraction else {}, i)
            if tr.llm is not None:
                s["tabel_visi"].add(table_label, tr.llm.values, i)
        pair_values = {"pola+llm": (det, llm_values),
                       "graf+pola": (graph_result.values if graph_result else None, det),
                       "graf+llm": (graph_result.values if graph_result else None, llm2.values if llm2 else None)}[pair.name]
        if pair_values[0] is not None and pair_values[1] is not None:
            s["sepakat"].add(text_label, agrees(_text_only(pair_values[0]), _text_only(pair_values[1])), i)
        correct = th == info.get("tahun_berlaku")
        g6[info["set"]]["benar" if correct else "salah"] += 1
        if not correct:
            g6_wrong.append(f"{i}: terbaca {th} ({note}), label {info.get('tahun_berlaku')}")
        replay[i] = {
            "set": info["set"], "det": {k: _s(v) for k, v in det.items()},
            "llm": {k: _s(v) for k, v in llm.values.items()} if llm else None,
            "llm_dibuang": llm.dropped if llm else [], "llm_token": llm.tokens if llm else 0,
            "tahun_berlaku": th, "tahun_berlaku_label": info.get("tahun_berlaku"),
        }
        all_cases += cases
        if progress:
            progress(n, i)
    return {
        "replay": replay,
        "skor": {s: {k: v.summary() for k, v in x.items()} for s, x in scores.items()},
        "rincian_salah": {s: {k: v.wrong for k, v in x.items()} for s, x in scores.items()},
        "rincian_terlewat": {s: {k: v.missed for k, v in x.items()} for s, x in scores.items()},
        "g6": {s: dict(c) for s, c in g6.items()}, "g6_salah": g6_wrong,
        "mutasi": [k.__dict__ for k in all_cases],
        "llm": pair.client is not None, "pasangan": pair.name,
    }


def _s(v):
    return None if v is None else str(v)


def summarize_mutations(cases: list[dict]) -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = {}
    for k in cases:
        r = out.setdefault(k["set"], {}).setdefault(k["jenis"], Counter())
        r["n"] += 1
        r[k["keputusan"]] += 1
        r["salah_lolos"] += k["salah_lolos"]
        r["draf_salah"] += k.get("draf_salah", False)
        r["llm_salah"] += k.get("llm_salah", False)
        r["sepakat_saja_lolos"] += bool(k.get("draf_salah")) and "G4" not in k["menahan"]
        if k.get("penahan_tunggal"):
            r[f"tunggal_{k['penahan_tunggal']}"] += 1
        for g in k["menahan"]:
            r[f"menahan_{g}"] += 1
    return {s: {j: dict(c) for j, c in x.items()} for s, x in out.items()}


def _pct(x) -> str:
    return "-" if x is None else f"{x * 100:.1f}%"


def markdown_report(h: dict, meta: dict) -> str:
    b = [
        "# Evaluasi Fase 2: draf tarif dan gerbang",
        "",
        f"Dibuat oleh `pph21 draft-evaluate`. Pasangan G4: {h.get('pasangan', 'pola+llm')}. Model LLM: {meta.get('model', '-')}"
        f"{', LLM kedua: ' + meta['model2'] if meta.get('model2') else ''}, prompt {meta.get('prompt', '-')}. "
        "Label: `taxagent/taxes/pph21/data/draf_label.yaml` (belum ada penilai kedua).",
        "",
        "## 1. Replay ekstraksi (per angka)",
        "",
        "| set | ekstraktor | benar | salah | terlewat | presisi | recall |",
        "|---|---|---|---|---|---|---|",
    ]
    for s, x in h["skor"].items():
        for e, r in x.items():
            empty = r["benar"] + r["salah"] + r["terlewat"] == 0
            if e != "det" and (empty or (not h["llm"] and e not in ("tabel_ocr", "tabel_visi"))):
                continue
            b.append(f"| {s} | {e} | {r['benar']} | {r['salah']} | {r['terlewat']} | {_pct(r['presisi'])} | {_pct(r['recall'])} |")
    b += ["", "`det` = pola regex; `llm` = LLM jendela teks; `graf` = LLM lewat bukti graf; `llm2` = LLM kedua; "
          "`sepakat` = angka yang dibaca SAMA oleh kedua ekstraktor pasangan G4 (yang bisa lolos gerbang); "
          "`tabel_ocr` / `tabel_visi` = tabel TER lampiran dibaca dari PDF JDIH (OCR kotak / LLM vision), dinilai "
          "terpisah; ekstraktor teks dinilai tanpa daun tabel.", ""]
    sources = meta.get("sumber_teks") or {}
    if sources:
        c = Counter(sources.values())
        b += ["Sumber teks (urutan sistem terpasang: JDIH andal, pajak.go.id, JDIH perlu_dicek): "
              + ", ".join(f"{k} {n}" for k, n in sorted(c.items())) + "."]
        if meta.get("tabel_lampiran"):
            b.append(f"Tabel lampiran: {meta['tabel_lampiran']}.")
        b.append("")
    for s in ("dev", "uji"):
        for e in ("det", "llm", "graf", "llm2", "sepakat", "tabel_ocr", "tabel_visi"):
            wrong = h["rincian_salah"][s].get(e)
            if wrong:
                b += [f"Salah ({s}, {e}):", ""] + [f"- {x}" for x in wrong] + [""]
    b += ["## 2. Tanggal berlaku (G6)", "", "| set | benar | salah |", "|---|---|---|"]
    for s, c in h["g6"].items():
        b.append(f"| {s} | {c.get('benar', 0)} | {c.get('salah', 0)} |")
    if h["g6_salah"]:
        b += [""] + [f"- {x}" for x in h["g6_salah"]]
    rm = summarize_mutations(h["mutasi"])
    if rm:
        b += [
            "", "## 3. Mutasi", "",
            "| set | jenis | n | siap | tahan | tidak ada perubahan | ditolak | dilewati | **salah lolos** | gerbang yang menahan |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for s, x in rm.items():
            for j in MUTATION_KINDS:
                if j not in x:
                    continue
                r = x[j]
                gates = ", ".join(f"{k[8:]} {v}" for k, v in sorted(r.items()) if k.startswith("menahan_"))
                b.append(f"| {s} | {j} | {r['n']} | {r.get('siap', 0)} | {r.get('tahan', 0)} | "
                         f"{r.get('tidak_ada_perubahan', 0)} | {r.get('ditolak', 0)} | {r.get('dilewati', 0)} | "
                         f"**{r.get('salah_lolos', 0)}** | {gates or '-'} |")
        b += ["", "### Pembanding (dari run yang sama, tanpa panggilan LLM tambahan)", "",
              "Nilai salah yang masuk tabel bila draf diterima tanpa gerbang (pola saja), bila bacaan LLM diterima "
              "langsung (LLM saja), dan bila hanya kesepakatan dua ekstraktor (G4) yang dipakai. Penahan tunggal: "
              "draf salah yang hanya ditahan satu gerbang; mematikan gerbang itu meloloskannya.", "",
              "| set | jenis | n | salah lolos (G1-G8) | pola saja | LLM saja | G4 saja | penahan tunggal |",
              "|---|---|---|---|---|---|---|---|"]
        for s, x in rm.items():
            for j in MUTATION_KINDS:
                if j not in x:
                    continue
                r = x[j]
                solo = ", ".join(f"{k[8:]} {v}" for k, v in sorted(r.items()) if k.startswith("tunggal_"))
                b.append(f"| {s} | {j} | {r['n']} | {r.get('salah_lolos', 0)} | {r.get('draf_salah', 0)} | "
                         f"{r.get('llm_salah', 0)} | {r.get('sepakat_saja_lolos', 0)} | {solo or '-'} |")
        passed = [k for k in h["mutasi"] if k["salah_lolos"]]
        if passed:
            b += ["", "Salah lolos:", ""] + [f"- {k['dokumen']} {k['jenis']} {k['angka']}: {k['catatan']}" for k in passed]
    return "\n".join(b) + "\n"
