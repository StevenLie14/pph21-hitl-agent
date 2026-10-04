from __future__ import annotations

import datetime as _dt
import json
import math
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..taxes import get as tax_module
from .classify import Watchlist, classify, load_watchlist
from .identity import canon_id

DATA_DIR = tax_module().data_dir

EVAL_FILE = DATA_DIR / "pantau_evaluasi.yaml"
LABELS = ("dasar", "fasilitas", "prosedural", "tidak_relevan")
PREDICTIONS = ("dasar", "fasilitas", "prosedural", "perlu_ditinjau", "tidak_relevan")


@dataclass
class EvalItem:
    set: str
    id: str
    title: str
    label: str
    subject: str = ""
    date: str = ""


@dataclass
class Prediction:
    item: EvalItem
    category: str
    reasons: list[str]

    @property
    def is_positive(self) -> bool:
        return self.category != "tidak_relevan"

    @property
    def label_is_positive(self) -> bool:
        return self.item.label != "tidak_relevan"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    half_width = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, center - half_width), min(1.0, center + half_width))


@dataclass
class Score:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    @property
    def precision(self) -> float | None:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else None

    @property
    def recall(self) -> float | None:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else None

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p and r else None

    def summary(self) -> dict:
        return {
            "tp": self.tp, "fp": self.fp, "fn": self.fn, "tn": self.tn,
            "presisi": self.precision, "recall": self.recall, "f1": self.f1,
            "presisi_ci95": wilson(self.tp, self.tp + self.fp),
            "recall_ci95": wilson(self.tp, self.tp + self.fn),
        }


@dataclass
class SetResult:
    name: str
    predictions: list[Prediction] = field(default_factory=list)

    def binary(self) -> Score:
        s = Score()
        for p in self.predictions:
            if p.is_positive and p.label_is_positive:
                s.tp += 1
            elif p.is_positive:
                s.fp += 1
            elif p.label_is_positive:
                s.fn += 1
            else:
                s.tn += 1
        return s

    def per_category(self) -> dict[str, Score]:
        result = {}
        for cat in LABELS[:3]:
            s = Score()
            for p in self.predictions:
                actual, guess = p.item.label == cat, p.category == cat
                s.tp += actual and guess
                s.fp += guess and not actual
                s.fn += actual and not guess
                s.tn += not actual and not guess
            result[cat] = s
        return result

    def confusion(self) -> dict[str, dict[str, int]]:
        c = Counter((p.item.label, p.category) for p in self.predictions)
        return {lab: {pred: c[(lab, pred)] for pred in PREDICTIONS} for lab in LABELS}

    @property
    def salah(self) -> list[Prediction]:
        return [p for p in self.predictions if p.is_positive != p.label_is_positive]


def load_set(path: Path | None = None) -> dict[str, list[EvalItem]]:
    data = yaml.safe_load(Path(path or EVAL_FILE).read_text(encoding="utf-8"))
    result = {}
    for name, entries in data.items():
        result[name] = [
            EvalItem(name, str(x["id"]), x["judul"], x["label"], x.get("perihal", ""), str(x.get("tanggal", "")))
            for x in entries
        ]
    return result


def without_self(wl: Watchlist, ident) -> Watchlist:
    if ident is None or wl.find(ident) is None:
        return wl
    return Watchlist(tuple(e for e in wl.regulations if e.identity != ident), wl.keywords, wl.keys_from_keywords)


def score_set(items: list[EvalItem], wl: Watchlist | None = None, prevent_leak: bool = True) -> SetResult:
    wl = wl or load_watchlist()
    result = SetResult(items[0].set if items else "")
    for it in items:
        ident = canon_id(it.id)
        w = without_self(wl, ident) if prevent_leak else wl
        k = classify(it.title, it.subject, ident, w)
        result.predictions.append(Prediction(it, k.category, list(k.reasons)))
    return result


def issued_since(items: list[EvalItem], since: str) -> list[EvalItem]:
    def iso(s: str) -> str | None:
        if m := re.fullmatch(r"(\d{4})-(\d{2})-(\d{2}).*", s or ""):
            return "-".join(m.groups())
        if m := re.fullmatch(r"(\d{2})-(\d{2})-(\d{4})", s or ""):
            return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        return None

    return [it for it in items if (d := iso(it.date)) and d >= since]


def evaluate(path: Path | None = None, prevent_leak: bool = True, since: str | None = None) -> dict[str, SetResult]:
    wl = load_watchlist()
    sets = load_set(path)
    if since:
        sets = {name: issued_since(items, since) for name, items in sets.items()}
    return {name: score_set(items, wl, prevent_leak) for name, items in sets.items()}


def score_llm(items: list[EvalItem], kl, workers: int = 4, progress=None) -> SetResult:
    result = SetResult(items[0].set if items else "")
    outputs = kl.classify_many([(it.id, it.title, it.subject) for it in items], workers, progress)
    for it, k in zip(items, outputs):
        result.predictions.append(Prediction(it, k.category, [k.reason] + ([] if k.valid else ["(jawaban tidak valid)"])))
    return result


_RE_ARTICLE_21 = re.compile(r"PASAL\s*21\b", re.I)


def _norm_title(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").upper()).strip()


def _number_year(s: str) -> tuple[int | None, str | None]:
    s = s or ""
    years = re.findall(r"(?:19|20)\d{2}", s)
    numbers = re.findall(r"\d+", s)
    return (int(numbers[0]) if numbers else None, years[-1] if years else None)


def texts_from_dataset(items: list[EvalItem], path: Path) -> dict[str, str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    index: dict[str, list[dict]] = {}
    for d in data:
        if (d.get("full_text") or "").strip():
            index.setdefault(_norm_title(d.get("title")), []).append(d)
    result = {}
    for it in items:
        candidates = index.get(_norm_title(it.title), [])
        if len(candidates) > 1:
            nt = _number_year(it.id)
            candidates = [d for d in candidates if _number_year(d.get("number")) == nt] or candidates
        if len(candidates) > 1 and it.date:
            candidates = [d for d in candidates if d.get("date") == it.date] or candidates
        if candidates:
            result[it.id] = max(candidates, key=lambda d: len(d.get("full_text") or ""))["full_text"]
    return result


def score_article21_text(items: list[EvalItem], texts: dict[str, str]) -> SetResult:
    result = SetResult(items[0].set if items else "")
    for it in items:
        t = texts.get(it.id)
        if t is None:
            result.predictions.append(Prediction(it, "tidak_relevan", ["tanpa teks"]))
        elif _RE_ARTICLE_21.search(t):
            result.predictions.append(Prediction(it, "perlu_ditinjau", ["teks menyebut Pasal 21"]))
        else:
            result.predictions.append(Prediction(it, "tidak_relevan", ["teks tidak menyebut Pasal 21"]))
    return result


def score_llm_text(items: list[EvalItem], kl, texts: dict[str, str], fallback: SetResult,
                   workers: int = 4, progress=None, cut=None) -> SetResult:
    from .classify_llm import excerpt

    cut = cut or excerpt
    with_text = [it for it in items if it.id in texts]
    outputs = kl.classify_many(
        [(it.id, it.title, it.subject, cut(texts[it.id])) for it in with_text], workers, progress
    )
    per_id = {it.id: k for it, k in zip(with_text, outputs)}
    previous = {p.item.id: p for p in fallback.predictions}
    result = SetResult(items[0].set if items else "")
    for it in items:
        k = per_id.get(it.id)
        if k is None:
            p = previous[it.id]
            result.predictions.append(Prediction(it, p.category, ["(tanpa teks: lengan judul)"] + list(p.reasons)))
        else:
            result.predictions.append(Prediction(it, k.category, [k.reason] + ([] if k.valid else ["(jawaban tidak valid)"])))
    return result


def combine_or(rules: SetResult, llm: SetResult) -> SetResult:
    result = SetResult(rules.name)
    for a, b in zip(rules.predictions, llm.predictions):
        assert a.item.id == b.item.id
        if a.is_positive or not b.is_positive:
            result.predictions.append(Prediction(a.item, a.category, list(a.reasons)))
        else:
            result.predictions.append(Prediction(a.item, b.category, ["LLM: " + "; ".join(b.reasons)]))
    return result


def mcnemar(a: SetResult, b: SetResult) -> dict:
    only_a = only_b = 0
    for x, y in zip(a.predictions, b.predictions):
        assert x.item.id == y.item.id
        bx, by = x.is_positive == x.label_is_positive, y.is_positive == y.label_is_positive
        only_a += bx and not by
        only_b += by and not bx
    n = only_a + only_b
    if n == 0:
        return {"hanya_a_benar": 0, "hanya_b_benar": 0, "p": 1.0}
    k = min(only_a, only_b)
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)
    return {"hanya_a_benar": only_a, "hanya_b_benar": only_b, "p": p}


def flip_rate(repeats: list[SetResult]) -> tuple[int, int]:
    if len(repeats) < 2:
        return (0, len(repeats[0].predictions) if repeats else 0)
    flipped = sum(
        len({p.is_positive for p in column}) > 1 for column in zip(*(h.predictions for h in repeats))
    )
    return (flipped, len(repeats[0].predictions))


def comparison_report_md(arms: dict[str, dict[str, SetResult]], meta: dict, llm_repeats: dict[str, list[SetResult]] | None = None) -> str:
    b = ["# Evaluasi pemantau: lengan aturan vs LLM vs hibrida", ""]
    b += [f"- {k}: {v}" for k, v in meta.items()]
    b += ["", "## Biner (perlu ditinjau atau tidak), CI95 Wilson", ""]
    b.append("| set | lengan | ditandai | TP | FP | FN | presisi [CI95] | recall [CI95] | F1 |")
    b.append("|---|---|---|---|---|---|---|---|---|")
    set_names = list(next(iter(arms.values())).keys())
    for ns in set_names:
        for nl, per_set in arms.items():
            s = per_set[ns].binary()
            r = s.summary()
            b.append(
                f"| {ns} | {nl} | {s.tp + s.fp} | {s.tp} | {s.fp} | {s.fn} | "
                f"{_pct(s.precision)} {_ci(r['presisi_ci95'])} | {_pct(s.recall)} {_ci(r['recall_ci95'])} | {_pct(s.f1)} |"
            )
    arm_names = list(arms)
    b += ["", "## McNemar eksak (kebenaran biner berpasangan)", ""]
    b.append("| set | A | B | hanya A benar | hanya B benar | p |")
    b.append("|---|---|---|---|---|---|")
    for ns in set_names:
        for i, la in enumerate(arm_names):
            for lb in arm_names[i + 1:]:
                m = mcnemar(arms[la][ns], arms[lb][ns])
                b.append(f"| {ns} | {la} | {lb} | {m['hanya_a_benar']} | {m['hanya_b_benar']} | {m['p']:.4f} |")
    if llm_repeats:
        b += ["", "## Variansi LLM antar-ulangan (temperature 0)", ""]
        for ns, entries in llm_repeats.items():
            flipped, n = flip_rate(entries)
            recall = ", ".join(_pct(h.binary().recall) for h in entries)
            b.append(f"- {ns}: {len(entries)} ulangan, keputusan biner berbalik pada {flipped}/{n} item; recall per ulangan: {recall}")
    for ns in set_names:
        positives = [p.item for p in arms[arm_names[0]][ns].predictions if p.label_is_positive]
        if not positives:
            continue
        b += ["", f"## Positif di set `{ns}`: siapa yang menangkap", ""]
        b.append("| id | label | " + " | ".join(arm_names) + " | judul |")
        b.append("|---|---|" + "---|" * len(arm_names) + "---|")
        pred = {nl: {p.item.id: p for p in arms[nl][ns].predictions} for nl in arm_names}
        for it in positives:
            sel = " | ".join(pred[nl][it.id].category if pred[nl][it.id].is_positive else "**lewat**" for nl in arm_names)
            b.append(f"| `{it.id}` | {it.label} | {sel} | {it.title[:90]} |")
    return "\n".join(b) + "\n"


def comparison_summary_json(arms: dict[str, dict[str, SetResult]], meta: dict) -> dict:
    return {
        "meta": meta,
        "lengan": {
            nl: {
                ns: {
                    "biner": h.binary().summary(),
                    "per_kategori": {k: s.summary() for k, s in h.per_category().items()},
                    "prediksi": [
                        {"id": p.item.id, "label": p.item.label, "prediksi": p.category, "alasan": p.reasons}
                        for p in h.predictions
                    ],
                }
                for ns, h in per_set.items()
            }
            for nl, per_set in arms.items()
        },
    }


def _date(s: str | None) -> _dt.date | None:
    if not s:
        return None
    try:
        return _dt.date.fromisoformat(s[:10])
    except ValueError:
        return None


def enrichment_sample(documents, fetch, limit: int = 0, progress=None) -> list[dict]:
    from .enrichment import enrich

    records = []
    entries = [d for d in documents if not d.artikel]
    for i, d in enumerate(entries[:limit] if limit else entries):
        p = enrich(d.slug, fetch, d.identity)
        h, t = p.page, p.text
        records.append({
            "id": str(d.identity), "slug": d.slug, "tanggal_feed": d.date,
            "portal_penetapan": h.tgl_penetapan if h else None,
            "portal_pengundangan": h.tgl_pengundangan if h else None,
            "relasi": [
                {"arah": r.arah, "jenis": r.jenis_efek, "nomor": r.nomor, "mulai": r.tgl_mulai_berlaku}
                for r in (h.relasi if h else [])
            ],
            "teks_ditetapkan": t.enacted if t else None,
            "teks_diundangkan": t.promulgated if t else None,
            "diundangkan_metadata": t.promulgated_metadata if t else None,
            "keputusan": t.is_decree if t else None,
            "teks_mulai": (t.mulai_berlaku_tanggal or t.in_force_from) if t else None,
            "berlaku_untuk": list(t.applies_to) if t else [],
            "retroaktif": t.retroaktif if t else None,
            "dicabut": [str(x.identitas) + (" (sebagian)" if x.sebagian else "") for x in t.revokes] if t else [],
            "diubah": [str(x) for x in t.amends] if t else [],
            "url_teks": p.text_url, "selisih": p.discrepancies, "galat": p.error,
        })
        if progress:
            progress(i + 1, d)
    return records


def enrichment_stats(records: list[dict]) -> dict:
    gaps, kinds = [], Counter()
    docs_with_diff = docs_with_text = retro = metadata = feed_is_enactment = 0
    for r in records:
        feed = _date(r.get("tanggal_feed"))
        enacted = _date(r.get("teks_ditetapkan")) or _date(r.get("portal_penetapan"))
        promulgated = _date(r.get("teks_diundangkan")) or _date(r.get("diundangkan_metadata")) or _date(r.get("portal_pengundangan"))
        feed_is_enactment += bool(feed and enacted and feed == enacted)
        if feed and promulgated:
            gaps.append((feed - promulgated).days)
        if r.get("teks_diundangkan") or r.get("teks_mulai") or r.get("teks_ditetapkan"):
            docs_with_text += 1
        metadata += bool(r.get("diundangkan_metadata"))
        retro += bool(r.get("retroaktif"))
        info = [s for s in r.get("selisih", []) if s.startswith("info:")]
        if info:
            kinds["info (perubahan antara tercakup)"] += len(info)
        meaningful = [s for s in r.get("selisih", []) if not s.startswith(("berlaku surut", "info:"))]
        docs_with_diff += bool(meaningful)
        for s in meaningful:
            if "dua metadata portal" in s:
                kinds["metadata portal tidak konsisten"] += 1
                continue
            kinds[next((k for k in ("tanggal penetapan", "tanggal pengundangan", "mulai berlaku", "pencabutan") if s.startswith(k)), "lain")] += 1
    result = {
        "dokumen": len(records),
        "teks_terbaca": docs_with_text,
        "dokumen_dengan_selisih": docs_with_diff,
        "selisih_per_jenis": dict(kinds),
        "berlaku_surut": retro,
        "pengundangan_dari_metadata": metadata,
        "keputusan_tanpa_pengundangan": sum(bool(r.get("keputusan")) for r in records),
        "galat": sum(bool(r.get("galat")) for r in records),
        "tanggal_feed_sama_penetapan": feed_is_enactment,
    }
    if gaps:
        ordered = sorted(gaps)
        result["tanggal_feed_minus_pengundangan_hari"] = {
            "n": len(ordered), "min": ordered[0], "median": statistics.median(ordered),
            "p90": ordered[min(len(ordered) - 1, math.ceil(0.9 * len(ordered)) - 1)], "maks": ordered[-1],
        }
    return result


def status_latency(notes) -> list[int]:
    result = []
    for c in notes:
        a, b = _date(c.first_seen), _date(c.diundangkan)
        if a and b:
            result.append((a - b).days)
    return result


def _pct(x: float | None) -> str:
    return "-" if x is None else f"{100 * x:.1f}%"


def _ci(ci: tuple[float, float]) -> str:
    return f"[{100 * ci[0]:.0f}-{100 * ci[1]:.0f}%]"


def markdown_report(result: dict[str, SetResult], enrichment: dict | None = None) -> str:
    b = ["# Evaluasi pemantau regulasi PPh 21", ""]
    b.append("## Biner: perlu ditinjau atau tidak")
    b.append("")
    b.append("| set | n | positif | ditandai | TP | FP | FN | presisi [CI95] | recall [CI95] | F1 |")
    b.append("|---|---|---|---|---|---|---|---|---|---|")
    for name, h in result.items():
        s = h.binary()
        r = s.summary()
        b.append(
            f"| {name} | {len(h.predictions)} | {s.tp + s.fn} | {s.tp + s.fp} | {s.tp} | {s.fp} | {s.fn} | "
            f"{_pct(s.precision)} {_ci(r['presisi_ci95'])} | {_pct(s.recall)} {_ci(r['recall_ci95'])} | {_pct(s.f1)} |"
        )
    for name, h in result.items():
        b += ["", f"## Set `{name}`", "", "Per kategori:", "", "| kategori | TP | FP | FN | presisi | recall | F1 |", "|---|---|---|---|---|---|---|"]
        for cat, s in h.per_category().items():
            b.append(f"| {cat} | {s.tp} | {s.fp} | {s.fn} | {_pct(s.precision)} | {_pct(s.recall)} | {_pct(s.f1)} |")
        b += ["", "Matriks konfusi (baris = label, kolom = prediksi):", ""]
        b.append("| label \\ prediksi | " + " | ".join(PREDICTIONS) + " |")
        b.append("|---|" + "---|" * len(PREDICTIONS))
        for lab, row in h.confusion().items():
            b.append(f"| {lab} | " + " | ".join(str(row[p]) for p in PREDICTIONS) + " |")
        if h.salah:
            b += ["", "Kesalahan biner:", ""]
            for p in h.salah:
                kind = "FN" if p.label_is_positive else "FP"
                b.append(f"- {kind} `{p.item.id}` (label {p.item.label}, prediksi {p.category}): {p.item.title[:110]}")
    if enrichment:
        b += ["", "## Sampel pengayaan feed (teks vs metadata JDIH)", "", "```", yaml.safe_dump(enrichment, allow_unicode=True, sort_keys=False).strip(), "```"]
    return "\n".join(b) + "\n"


def summary_json(result: dict[str, SetResult], enrichment: dict | None = None) -> dict:
    return {
        "set": {
            name: {
                "n": len(h.predictions),
                "biner": h.binary().summary(),
                "per_kategori": {k: s.summary() for k, s in h.per_category().items()},
                "konfusi": h.confusion(),
                "salah": [
                    {"id": p.item.id, "label": p.item.label, "prediksi": p.category, "judul": p.item.title, "alasan": p.reasons}
                    for p in h.salah
                ],
            }
            for name, h in result.items()
        },
        "pengayaan": enrichment,
    }
