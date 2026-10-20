from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from ..agent.numbers import amounts, numbers_in, unsourced
from ..taxes import get as tax_module
from ..tools import all_tool_names, call_tool

if TYPE_CHECKING:
    from ..agent.runner import AgentTurn, ToolCall

DATA_DIR = tax_module().data_dir

CASES_FILE = DATA_DIR / "kasus_agent.yaml"
BEHAVIOURS = ("hitung", "tanya_balik", "tolak", "info", "graf")


def load_cases(path: Path | None = None) -> list[dict]:
    data = yaml.safe_load(Path(path or CASES_FILE).read_text(encoding="utf-8"))
    case = data["kasus"]
    for k in case:
        if k.get("perilaku") not in BEHAVIOURS:
            raise ValueError(f"kasus {k.get('id')}: perilaku harus salah satu dari {BEHAVIOURS}")
    return case


def apply_original_questions(cases: list[dict], path: Path) -> int:
    original = (yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}).get("kasus", {})
    replaced = 0
    for case in cases:
        item = original.get(case["id"])
        if item and item.get("pertanyaan"):
            case["pertanyaan"] = item["pertanyaan"]
            case["pertanyaan_asli"] = True
            replaced += 1
    return replaced


def reference_result(case: dict) -> dict | None:
    if case["perilaku"] != "hitung":
        return None
    result = call_tool(case["tool"], **case["argumen"])
    if not result.get("berhasil"):
        raise ValueError(f"kasus {case['id']}: argumen harapan ditolak mesin hitung: {result}")
    return result


def _number(v) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.replace("_", "").strip())
        except ValueError:
            return None
    return None


def matches(expected: Any, actual: Any) -> bool:
    if isinstance(expected, bool):
        if isinstance(actual, str):
            return actual.strip().lower() == str(expected).lower()
        return isinstance(actual, bool) and actual == expected
    h, a = _number(expected), _number(actual)
    if h is not None:
        return a is not None and abs(h - a) < 0.5
    return str(expected).strip().lower() == str(actual).strip().lower()


@dataclass
class CaseResult:
    id: str
    kategori: str
    tag: list[str]
    perilaku: str
    tool_harapan: str | None
    tool_dipanggil: list[str] = field(default_factory=list)
    tool_hitung_pertama: str | None = None
    tool_hitung_akhir: str | None = None
    tool_benar: bool = False
    tool_benar_percobaan_pertama: bool = False
    argumen_benar: bool | None = None
    field_benar: int = 0
    field_total: int = 0
    argumen_salah: dict = field(default_factory=dict)
    argumen_aktual: dict = field(default_factory=dict)
    pph_harapan: str | None = None
    pph_aktual: str | None = None
    angka_benar: bool | None = None
    perilaku_benar: bool = False
    galat_tool: int = 0
    tool_halusinasi: list[str] = field(default_factory=list)
    putaran: int = 0
    detik: float = 0.0
    jawaban: str = ""
    error: str | None = None
    galat_api: list[str] = field(default_factory=list)
    perilaku_benar_satu_giliran: bool = False
    tool_graf: int = 0
    klarifikasi: bool = False
    sitasi_belum_terverifikasi: list[str] = field(default_factory=list)
    sitasi_diperiksa: bool = True
    sitasi_audit_ablasi: list[str] = field(default_factory=list)
    sitasi_dikoreksi: list[str] = field(default_factory=list)
    status_distempel: list[str] = field(default_factory=list)
    angka_tanpa_sumber: list[int] = field(default_factory=list)
    pph_di_jawaban: bool | None = None
    token_masuk: int = 0
    token_keluar: int = 0
    jejak: list[dict] = field(default_factory=list)


_amounts = amounts
_numbers_in = numbers_in


def number_faithfulness(answer: str, trace: list[ToolCall], case: dict) -> tuple[list[int], bool | None]:
    sources = _numbers_in([j.result for j in trace]) | _numbers_in(
        [v for v in case.values() if isinstance(v, (str, list))])
    missing = unsourced(answer, sources)
    calcs = [j for j in trace if _is_calculation(j.name) and _succeeded(j.result)]
    pph = None
    if calcs and scored_amount(calcs[-1].result) is not None:
        value = round(float(scored_amount(calcs[-1].result)))
        pph = value < 1000 or bool({value - 1, value, value + 1} & _amounts(answer)) or str(value) in answer
    return missing, pph


def scored_amount(result: dict) -> Any:
    for k in ("pph_terutang", "natura_kena_pajak"):
        if result.get(k) is not None:
            return result[k]
    return None


def _str_or_none(v: Any) -> str | None:
    return None if v is None else str(v)


def _is_calculation(name: str) -> bool:
    return name.startswith("calculate_")


def _succeeded(result: Any) -> bool:
    return isinstance(result, dict) and bool(result.get("berhasil"))


def contains_key_facts(answer: str, case: dict) -> bool:
    for item in case.get("harus_memuat", []):
        options = item if isinstance(item, list) else [item]
        if not any(str(o).lower() in answer for o in options):
            return False
    return True


RESULT_CHARS = 8000


def _trace_record(trace: list[ToolCall]) -> list[dict]:
    out = []
    for j in trace:
        text = json.dumps(j.result, ensure_ascii=False, default=str)
        result = json.loads(text) if len(text) <= RESULT_CHARS else {"terpotong": True, "teks": text[:RESULT_CHARS]}
        out.append({"tool": j.name, "argumen": json.loads(json.dumps(j.arguments or {}, ensure_ascii=False,
                                                                     default=str)), "hasil": result})
    return out


def score_case(case: dict, turn: AgentTurn | _Combined, seconds: float, reference: dict | None) -> CaseResult:
    trace: list[ToolCall] = list(turn.trace)
    known = set(all_tool_names())
    h = CaseResult(
        id=case["id"],
        kategori=case.get("kategori", ""),
        tag=list(case.get("tag", [])),
        perilaku=case["perilaku"],
        tool_harapan=case.get("tool"),
        tool_dipanggil=[j.name for j in trace],
        galat_tool=sum(1 for j in trace if isinstance(j.result, dict) and j.result.get("berhasil") is False),
        tool_halusinasi=[j.name for j in trace if j.name not in known],
        putaran=turn.rounds,
        detik=round(seconds, 2),
        jawaban=(turn.answer or "")[:6000],
        sitasi_belum_terverifikasi=list(getattr(turn, "citation_unverified", [])),
        sitasi_diperiksa=getattr(turn, "citation_checked", True),
        sitasi_audit_ablasi=list(getattr(turn, "citation_audit", [])),
        sitasi_dikoreksi=list(getattr(turn, "citation_corrections", [])),
        status_distempel=list(getattr(turn, "status_stamped", [])),
        token_masuk=getattr(turn, "tokens_in", 0),
        token_keluar=getattr(turn, "tokens_out", 0),
        jejak=_trace_record(trace),
    )
    h.angka_tanpa_sumber, h.pph_di_jawaban = number_faithfulness(turn.answer or "", trace, case)

    calcs = [j for j in trace if _is_calculation(j.name)]
    successful_calcs = [j for j in calcs if _succeeded(j.result)]
    from ..tools.registry import graph_tool_names

    graph_calls = [j for j in trace if j.name in graph_tool_names()]
    h.tool_graf = len(graph_calls)
    if calcs:
        h.tool_hitung_pertama = calcs[0].name
        h.tool_hitung_akhir = (successful_calcs or calcs)[-1].name

    if case["perilaku"] in ("tanya_balik", "tolak"):
        h.tool_benar = not successful_calcs
        h.tool_benar_percobaan_pertama = not calcs
        h.perilaku_benar = h.tool_benar
        return h

    if case["perilaku"] == "graf":
        answer = (turn.answer or "").lower()
        valid_tools = set(graph_tool_names()) | set(case.get("tool_alternatif", []))
        h.tool_benar = any(_succeeded(j.result) for j in trace if j.name in valid_tools)
        h.tool_benar_percobaan_pertama = bool(trace) and trace[0].name in valid_tools
        h.perilaku_benar = h.tool_benar and not successful_calcs and contains_key_facts(answer, case)
        return h

    if case["perilaku"] == "info":
        h.tool_benar = case["tool"] in h.tool_dipanggil
        h.tool_benar_percobaan_pertama = bool(trace) and trace[0].name == case["tool"]
        h.perilaku_benar = (h.tool_benar and not successful_calcs
                            and contains_key_facts((turn.answer or "").lower(), case))
        return h

    tool = case["tool"]
    h.tool_benar = h.tool_hitung_akhir == tool
    h.tool_benar_percobaan_pertama = h.tool_hitung_pertama == tool
    h.pph_harapan = _str_or_none(scored_amount(reference)) if reference else None

    candidates = [j for j in calcs if j.name == tool]
    if not candidates:
        h.argumen_benar = False
        h.angka_benar = False
        return h
    scored = [j for j in candidates if _succeeded(j.result)] or candidates
    call = scored[-1]
    h.argumen_aktual = dict(call.arguments)

    keys = case.get("argumen_dinilai") or list(case["argumen"])
    for k in keys:
        expected = case["argumen"][k]
        actual = call.arguments.get(k, _default_schema(tool, k))
        h.field_total += 1
        if matches(expected, actual):
            h.field_benar += 1
        else:
            h.argumen_salah[k] = {"harapan": expected, "aktual": actual}
    h.argumen_benar = not h.argumen_salah

    if _succeeded(call.result):
        h.pph_aktual = _str_or_none(scored_amount(call.result))
    h.angka_benar = h.pph_aktual is not None and h.pph_aktual == h.pph_harapan
    h.perilaku_benar = h.tool_benar and bool(h.angka_benar)
    return h


def _default_schema(tool: str, field_name: str) -> Any:
    from ..tools import TOOL_SPECS

    for fn, args, _ in TOOL_SPECS:
        if fn.__name__ == tool:
            f = args.model_fields.get(field_name)
            if f is not None and not f.is_required():
                return f.default
    return None


CLARIFICATION_REPLY = (
    "Pakai default saja untuk semua yang Anda tanyakan. Tidak ada data lain selain "
    "yang sudah saya sebutkan; silakan langsung hitung."
)


@dataclass
class _Combined:
    answer: str
    trace: list[ToolCall]
    rounds: int
    citation_unverified: list[str] = field(default_factory=list)
    citation_checked: bool = True
    citation_audit: list[str] = field(default_factory=list)
    citation_corrections: list[str] = field(default_factory=list)
    status_stamped: list[str] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0

    @classmethod
    def of(cls, first, second) -> _Combined:
        def get(turn, name, default):
            return getattr(turn, name, default)

        return cls(answer=second.answer, trace=list(first.trace) + list(second.trace),
                   rounds=first.rounds + second.rounds,
                   citation_unverified=list(get(second, "citation_unverified", [])),
                   citation_checked=get(second, "citation_checked", True),
                   citation_audit=list(get(first, "citation_audit", [])) + list(get(second, "citation_audit", [])),
                   citation_corrections=list(get(first, "citation_corrections", []))
                   + list(get(second, "citation_corrections", [])),
                   status_stamped=list(get(second, "status_stamped", [])),
                   tokens_in=max(get(first, "tokens_in", 0), get(second, "tokens_in", 0)),
                   tokens_out=max(get(first, "tokens_out", 0), get(second, "tokens_out", 0)))


def _without_calculation(turn: AgentTurn) -> bool:
    return not any(_is_calculation(j.name) and _succeeded(j.result) for j in turn.trace)


def run_cases(
    cases: Iterable[dict],
    make_agent: Callable[[], Any],
    on_done: Callable[[CaseResult], None] | None = None,
    retries: int = 3,
    retry_delay: float = 5.0,
    clarify: bool = True,
    retry_rounds: int = 0,
    round_delay: float = 60.0,
) -> list[CaseResult]:
    cases = list(cases)
    result = []
    for case in cases:
        result.append(_run_one(case, make_agent, retries, retry_delay, clarify, []))
        if on_done:
            on_done(result[-1])
    for _ in range(retry_rounds):
        failed = [i for i, h in enumerate(result) if h.error]
        if not failed:
            break
        time.sleep(round_delay)
        for i in failed:
            h = _run_one(cases[i], make_agent, retries, retry_delay, clarify, result[i].galat_api)
            result[i] = h
            if on_done:
                on_done(h)
    return result


def _run_one(case: dict, make_agent, retries: int, retry_delay: float, clarify: bool,
             seen: list[str]) -> CaseResult:
    ref = reference_result(case)
    seen = list(seen)
    for attempt in range(retries):
        try:
            agent = make_agent()
            start = time.perf_counter()
            first: AgentTurn = agent.ask(case["pertanyaan"])
            strict = score_case(case, first, 0.0, ref).perilaku_benar
            final, clarified = first, False
            if clarify and case["perilaku"] == "hitung" and _without_calculation(first):
                second: AgentTurn = agent.ask(CLARIFICATION_REPLY)
                final = _Combined.of(first, second)
                clarified = True
            seconds = time.perf_counter() - start
            h = score_case(case, final, seconds, ref)
            h.perilaku_benar_satu_giliran = strict
            h.klarifikasi = clarified
            h.galat_api = seen
            return h
        except Exception as exc:  # noqa: BLE001
            seen.append(f"{type(exc).__name__}: {exc}"[:500])
            time.sleep(retry_delay * (attempt + 1))
    return CaseResult(
        id=case["id"],
        kategori=case.get("kategori", ""),
        tag=list(case.get("tag", [])),
        perilaku=case["perilaku"],
        tool_harapan=case.get("tool"),
        pph_harapan=_str_or_none(scored_amount(ref)) if ref else None,
        error=seen[-1] if seen else "tidak diketahui",
        galat_api=seen,
    )


def _ratio(part: int, total: int) -> float | None:
    return round(part / total, 4) if total else None


def summarize(result: list[CaseResult]) -> dict:
    calcs = [h for h in result if h.perilaku == "hitung"]
    others = [h for h in result if h.perilaku != "hitung"]
    field_total = sum(h.field_total for h in calcs)

    def per(key_fn: Callable[[CaseResult], Iterable[str]]) -> dict:
        groups: dict[str, list[CaseResult]] = {}
        for h in result:
            for k in key_fn(h):
                groups.setdefault(k, []).append(h)
        return {
            k: {
                "n": len(v),
                "perilaku_benar": _ratio(sum(x.perilaku_benar for x in v), len(v)),
            }
            for k, v in sorted(groups.items())
        }

    return {
        "n_kasus": len(result),
        "n_error_api": sum(1 for h in result if h.error),
        "n_galat_api_diulang": sum(len(h.galat_api) for h in result if not h.error),
        "kasus_diulang": sorted({h.id for h in result if h.galat_api and not h.error}),
        "akurasi_keseluruhan": _ratio(sum(h.perilaku_benar for h in result), len(result)),
        "akurasi_satu_giliran": _ratio(sum(h.perilaku_benar_satu_giliran for h in result), len(result)),
        "klarifikasi_tidak_perlu": sum(1 for h in calcs if h.klarifikasi),
        "kasus_hitung_memanggil_graf": sum(1 for h in calcs if h.tool_graf),
        "token": {"masuk": sum(h.token_masuk for h in result), "keluar": sum(h.token_keluar for h in result),
                  "keluar_per_kasus": round(sum(h.token_keluar for h in result) / len(result), 1) if result else None},
        "hitung": {
            "n": len(calcs),
            "akurasi_tool": _ratio(sum(h.tool_benar for h in calcs), len(calcs)),
            "akurasi_tool_percobaan_pertama": _ratio(
                sum(h.tool_benar_percobaan_pertama for h in calcs), len(calcs)
            ),
            "akurasi_argumen_lengkap": _ratio(sum(bool(h.argumen_benar) for h in calcs), len(calcs)),
            "akurasi_field": _ratio(sum(h.field_benar for h in calcs), field_total),
            "akurasi_angka_akhir": _ratio(sum(bool(h.angka_benar) for h in calcs), len(calcs)),
        },
        "non_hitung": {
            "n": len(others),
            "akurasi": _ratio(sum(h.perilaku_benar for h in others), len(others)),
            "per_perilaku": {
                p: _ratio(
                    sum(h.perilaku_benar for h in others if h.perilaku == p),
                    sum(1 for h in others if h.perilaku == p),
                )
                for p in ("tanya_balik", "tolak", "info")
            },
        },
        "per_kategori": per(lambda h: [h.kategori]),
        "per_tag": per(lambda h: h.tag),
        "total_galat_tool": sum(h.galat_tool for h in result),
        "kasus_tool_halusinasi": sum(1 for h in result if h.tool_halusinasi),
        "jawaban_sitasi_bermasalah": sum(1 for h in result if h.sitasi_belum_terverifikasi or h.sitasi_audit_ablasi),
        "pemeriksa_sitasi": {
            "jawaban_dikoreksi": sum(1 for h in result if h.sitasi_dikoreksi),
            "masih_bermasalah_setelah_koreksi": sum(1 for h in result if h.sitasi_dikoreksi and h.sitasi_belum_terverifikasi),
            "jawaban_distempel_status": sum(1 for h in result if h.status_distempel),
        },
        "kesetiaan_angka": {
            "jawaban_dengan_angka_tanpa_sumber": sum(1 for h in result if h.angka_tanpa_sumber),
            "pph_tool_di_jawaban": _ratio(sum(1 for h in result if h.pph_di_jawaban),
                                          sum(1 for h in result if h.pph_di_jawaban is not None)),
        },
        "rata_putaran": round(sum(h.putaran for h in result) / len(result), 2) if result else None,
        "rata_detik": round(sum(h.detik for h in result) / len(result), 2) if result else None,
    }


def to_dicts(result: list[CaseResult]) -> list[dict]:
    return [asdict(h) for h in result]


def _percent(x: float | None) -> str:
    return "-" if x is None else f"{x * 100:.1f}%"


def markdown_report(meta: dict, summary: dict, result: list[CaseResult]) -> str:
    r, hi, nh = summary, summary["hitung"], summary["non_hitung"]
    lines = [
        f"# Evaluasi agent PPh 21: {meta.get('provider')} / {meta.get('model')}",
        "",
        f"Waktu: {meta.get('waktu')}. Kasus: {r['n_kasus']} "
        f"(galat API tersisa: {r['n_error_api']}; galat API yang diulang sampai terjawab: "
        f"{r.get('n_galat_api_diulang', 0)} pada {len(r.get('kasus_diulang', []))} kasus). "
        f"Dataset: `{meta.get('dataset')}`.",
        "",
        "## Ringkasan",
        "",
        "| Metrik | Nilai |",
        "|---|---|",
        f"| Akurasi keseluruhan (maks. 1 klarifikasi) | {_percent(r['akurasi_keseluruhan'])} |",
        f"| Akurasi ketat satu giliran | {_percent(r['akurasi_satu_giliran'])} |",
        f"| Token LLM masuk / keluar | {(r.get('token') or {}).get('masuk', 0)} / {(r.get('token') or {}).get('keluar', 0)} |",
        f"| Kasus hitung yang bertanya balik padahal data lengkap | {r['klarifikasi_tidak_perlu']} |",
        f"| Hitung: tool benar (akhir) | {_percent(hi['akurasi_tool'])} |",
        f"| Hitung: tool benar (percobaan pertama) | {_percent(hi['akurasi_tool_percobaan_pertama'])} |",
        f"| Hitung: semua argumen benar | {_percent(hi['akurasi_argumen_lengkap'])} |",
        f"| Hitung: akurasi per field | {_percent(hi['akurasi_field'])} |",
        f"| Hitung: angka akhir benar | {_percent(hi['akurasi_angka_akhir'])} |",
        f"| Tanya balik benar | {_percent(nh['per_perilaku']['tanya_balik'])} |",
        f"| Tolak (di luar cakupan) benar | {_percent(nh['per_perilaku']['tolak'])} |",
        f"| Info (cari dasar hukum) benar | {_percent(nh['per_perilaku']['info'])} |",
        f"| Total galat tool | {r['total_galat_tool']} |",
        f"| Kasus dengan tool halusinasi | {r['kasus_tool_halusinasi']} |",
        f"| Rata-rata putaran / detik | {r['rata_putaran']} / {r['rata_detik']} |",
        "",
        "## Per kategori",
        "",
        "| Kategori | n | Benar |",
        "|---|---|---|",
    ]
    lines += [f"| {k} | {v['n']} | {_percent(v['perilaku_benar'])} |" for k, v in r["per_kategori"].items()]
    if r["per_tag"]:
        lines += ["", "## Per tag", "", "| Tag | n | Benar |", "|---|---|---|"]
        lines += [f"| {k} | {v['n']} | {_percent(v['perilaku_benar'])} |" for k, v in r["per_tag"].items()]

    wrong = [h for h in result if not h.perilaku_benar]
    lines += ["", f"## Kasus yang salah ({len(wrong)})", ""]
    for h in wrong:
        lines.append(f"### {h.id} ({h.perilaku}, {h.kategori})")
        if h.error:
            lines.append(f"- Galat API: `{h.error}`")
        lines.append(f"- Tool harapan: `{h.tool_harapan}`; dipanggil: `{h.tool_dipanggil}`")
        if h.argumen_salah:
            for k, v in h.argumen_salah.items():
                lines.append(f"- Argumen `{k}`: harapan `{v['harapan']}`, aktual `{v['aktual']}`")
        if h.perilaku == "hitung":
            lines.append(f"- PPh harapan {h.pph_harapan}, aktual {h.pph_aktual}")
            if h.argumen_aktual:
                lines.append(f"- Argumen dikirim: `{h.argumen_aktual}`")
        short_answer = " ".join(h.jawaban.split())[:300]
        if short_answer:
            lines.append(f"- Jawaban: {short_answer}")
        lines.append("")
    return "\n".join(lines)
