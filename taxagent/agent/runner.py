from __future__ import annotations

import contextlib
import json
import logging
import os
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from ..settings import get_settings
from ..taxes import get as tax_module
from ..tools import langchain_tools

log = logging.getLogger(__name__)

DEFAULT_OPENAI_MODEL = get_settings().openai_model
MAX_TURNS = 8


class MissingApiKey(RuntimeError):
    pass


PROVIDERS = ("azure", "openai")


class UnsupportedProvider(ValueError):
    pass


def _check_provider(provider: str) -> str:
    provider = provider.lower()
    if provider not in PROVIDERS:
        raise UnsupportedProvider(f"Provider LLM '{provider}' tidak dipakai sistem ini; pilih {' atau '.join(PROVIDERS)}.")
    return provider


@dataclass
class ToolCall:
    name: str
    arguments: dict
    result: Any


@dataclass
class AgentTurn:
    answer: str
    trace: list[ToolCall] = field(default_factory=list)
    rounds: int = 0
    citation_corrections: list[str] = field(default_factory=list)
    citation_unverified: list[str] = field(default_factory=list)
    citation_checked: bool = True
    citation_audit: list[str] = field(default_factory=list)
    status_stamped: list[str] = field(default_factory=list)
    number_corrections: list[int] = field(default_factory=list)
    numbers_unsourced: list[int] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0

    def called_tool_names(self) -> list[str]:
        return [j.name for j in self.trace]


def _openai_key() -> str | None:
    return get_settings().openai_api_key


def _azure_key() -> str | None:
    return get_settings().azure_api_key


def default_provider() -> str:
    explicit = get_settings().llm_provider
    if explicit:
        return _check_provider(explicit)
    if _azure_key():
        return "azure"
    if _openai_key():
        return "openai"
    raise MissingApiKey(
        "Kunci API tidak ditemukan. Set AZURE_OPENAI_API_KEY (Azure AI Foundry) atau OPENAI_API_KEY (OpenAI) "
        "di environment atau di berkas .env. Perintah `pph21 calculate` dan seluruh "
        "test tidak memerlukan kunci ini."
    )


_NO_TEMPERATURE_MODELS = re.compile(r"^(o\d|gpt-5|gpt-6)", re.I)


def supports_temperature(model_name: str | None) -> bool:
    forced = get_settings().llm_force_no_temperature
    if forced in ("1", "0"):
        return forced == "0"
    return not (model_name and _NO_TEMPERATURE_MODELS.match(model_name))


def _sampling_options(model_name: str | None, temperature: float) -> dict:
    if supports_temperature(model_name):
        return {"temperature": temperature}
    return {"reasoning_effort": get_settings().llm_reasoning_effort or "none"}


_INSTALL_HINT = 'Jalankan: pip install -e ".[agent]"'


def _required(value: str | None, name: str) -> str:
    if not value:
        raise MissingApiKey(f"{name} tidak ditemukan di environment atau berkas .env.")
    return value


def build_model(model: str | None = None, temperature: float = 0.0, provider: str | None = None):
    provider = _check_provider(provider or default_provider())
    try:
        from langchain_openai import AzureChatOpenAI, ChatOpenAI
    except ImportError as exc:  # pragma: no cover
        raise ImportError(f"Paket langchain-openai belum terpasang. {_INSTALL_HINT}") from exc

    if provider == "openai":
        name = model or DEFAULT_OPENAI_MODEL
        key = _required(_openai_key(), "OPENAI_API_KEY")
        return ChatOpenAI(model=name, api_key=key, **_sampling_options(name, temperature))

    key = _required(_azure_key(), "AZURE_OPENAI_API_KEY")
    cfg = get_settings()
    endpoint = _required(cfg.azure_endpoint, "AZURE_OPENAI_ENDPOINT")
    deployment = _required(model or cfg.azure_deployment,
                           "AZURE_OPENAI_DEPLOYMENT (nama deployment di Azure AI Foundry)")
    return AzureChatOpenAI(
        azure_deployment=deployment,
        azure_endpoint=endpoint,
        api_version=cfg.azure_api_version,
        api_key=key,
        **_sampling_options(deployment, temperature),
    )


CITATION_NOTICE = ("[Pemeriksa sitasi otomatis, bukan pengguna] Jawabanmu menyebut peraturan yang tidak lolos "
                    "pemeriksaan. Perbaiki jawaban: sebut peraturan hanya bila muncul di hasil tool, dan bila peraturan "
                    "itu sudah dicabut/berakhir pada tanggal fakta, katakan statusnya atau rujuk penggantinya.\n")


UNKNOWN_REGULATION_NOTE = ("[Pemeriksaan otomatis, bukan pengguna] {regs} yang disebut pengguna tidak ada di graf "
                           "peraturan; permintaan pemeriksaan untuk pemantau sudah dicatat (jangan panggil "
                           "report_possibly_stale lagi untuknya). Jangan memakai angka dari pengguna. Hitung dengan data "
                           "kalkulator bila bisa, dan katakan bahwa data itu mungkin belum memuat peraturan tersebut.")
UNKNOWN_REGULATION_ANSWER = ("\n\nCatatan: {regs} yang Anda sebut belum ada di data sistem ini; permintaan pemeriksaan "
                             "sudah dicatat. Angka di atas memakai data yang tersedia dan mungkin belum memuat perubahan "
                             "dari peraturan itu.")

REPEALED_BASIS_NOTE = ("[Pemeriksaan otomatis, bukan pengguna] Dasar hukum hitungan ini sudah tidak berlaku pada "
                       "tanggalnya menurut graf: {regs}. Permintaan pemeriksaan untuk pemantau sudah dicatat (jangan "
                       "panggil report_possibly_stale lagi untuknya). Katakan statusnya dan bahwa angka memakai data "
                       "kalkulator yang mungkin belum mengikuti aturan penggantinya.")
REPEALED_BASIS_ANSWER = ("\n\nCatatan: dasar hukum hitungan di atas sudah tidak berlaku menurut graf peraturan ({regs}); "
                         "permintaan pemeriksaan sudah dicatat. Angka di atas memakai data kalkulator yang mungkin belum "
                         "mengikuti aturan penggantinya.")


NUMBER_NOTICE = ("[Pemeriksa angka otomatis, bukan pengguna] Jawabanmu memuat angka rupiah yang tidak berasal dari hasil "
                 "tool maupun pesan pengguna: {amounts}. Angka pajak hanya boleh dari tool. Hitung dengan tool yang "
                 "sesuai, atau hapus angka itu dan jelaskan tanpa menghitung bila tidak ada tool untuk itu.")
NUMBER_NOTE = ("\n\nCatatan pemeriksa angka otomatis: angka berikut tidak berasal dari kalkulator atau dari pesan Anda; "
               "jangan dipakai tanpa diperiksa: {amounts}.")
_NOTICES = ("[Pemeriksa sitasi otomatis", "[Pemeriksa angka otomatis")


def _rupiah(values: list[int]) -> str:
    return ", ".join("Rp" + f"{v:,}".replace(",", ".") for v in values)


UNVERIFIED_NOTE = ("\n\nCatatan pemeriksa sitasi otomatis: sitasi berikut belum terverifikasi; periksa sumbernya "
                   "sebelum dipakai.\n")
UNCHECKED_NOTE = ("\n\nCatatan: sitasi peraturan pada jawaban ini tidak diperiksa otomatis karena graf peraturan "
                  "tidak dapat dihubungi; periksa status peraturannya sebelum dipakai.")


def mark_citations(answer: str, problems: list[str] | None) -> str:
    if problems is None:
        return answer + UNCHECKED_NOTE
    if problems:
        return answer + UNVERIFIED_NOTE + "\n".join(f"- {m}" for m in problems)
    return answer


TURN_LIMIT_NOTICE = ("[Sistem, bukan pengguna] Batas pemanggilan tool tercapai. Jawab sekarang hanya dari hasil tool yang "
                 "sudah ada, tanpa memanggil tool lagi; katakan terus terang bagian yang belum sempat dicek.")


class TaxAgent:
    def __init__(
        self,
        model: str | None = None,
        temperature: float = 0.0,
        verbose: bool = False,
        llm=None,
        provider: str | None = None,
    ):
        from langchain_core.messages import SystemMessage

        self.tools = langchain_tools()
        self._tools_by_name = {t.name: t for t in self.tools}
        if llm is not None:
            self.llm = llm
        else:
            provider = (provider or default_provider()).lower()
            options = {"parallel_tool_calls": False} if provider in ("azure", "openai") else {}
            self.llm = build_model(model, temperature, provider).bind_tools(self.tools, **options)
        self.verbose = verbose
        self.riwayat: list = [SystemMessage(content=tax_module().system_prompt())]
        self.citation_audit: list[str] = []
        self._unknown: list[str] = []
        self._repealed: list[str] = []

    def _check_citations(self, answer: str, trace: list[ToolCall]) -> list[str] | None:
        import datetime as _dt

        from ..tools.registry import graph_tool_names

        graph_tools = graph_tool_names()
        self._unstated = []
        if not graph_tools & set(self._tools_by_name):
            return []
        from ..settings import get_settings
        from ..tools.regulation_graph import check_citations

        fact_date = next((j.arguments.get("tanggal") for j in reversed(trace)
                          if j.name in graph_tools and (j.arguments or {}).get("tanggal")), None)
        try:
            d = _dt.date.fromisoformat(fact_date[:10]) if fact_date else None
            problems = check_citations(answer, [j.result for j in trace], d)
            self._status_date = d
            self._unstated = self._unstated_status(answer, d)
            settings = get_settings()
            if settings.graph_ablation:
                self.citation_audit = problems + [f"{k} berstatus {st['status']} tetapi statusnya tidak disebut"
                                                  for k, st in self._unstated]
                self._unstated = []
                return []
            return problems
        except Exception:  # noqa: BLE001
            log.warning("citation check failed; answer returned marked as unchecked", exc_info=True)
            self._unstated = []
            return None

    @staticmethod
    def _unstated_status(answer: str, d) -> list[tuple[str, dict]]:
        from ..tools.regulation_graph import unstated_status

        return unstated_status(answer, d)

    def _invoke(self, messages, **kwargs):
        reply = self.llm.invoke(messages, **kwargs)
        usage = getattr(reply, "usage_metadata", None) or {}
        self.tokens_in = getattr(self, "tokens_in", 0) + int(usage.get("input_tokens", 0) or 0)
        self.tokens_out = getattr(self, "tokens_out", 0) + int(usage.get("output_tokens", 0) or 0)
        return reply

    def _answer_without_tools(self, trace: list[ToolCall]) -> tuple[str, list[str] | None] | None:
        from langchain_core.messages import AIMessage, HumanMessage

        messages = [*self.riwayat, HumanMessage(content=TURN_LIMIT_NOTICE)]
        for attempt in range(2):
            try:
                try:
                    reply = self._invoke(messages, tool_choice="none")
                except TypeError:
                    reply = self._invoke(messages)
            except Exception:  # noqa: BLE001
                log.warning("final answer after the tool-call limit failed", exc_info=True)
                return None
            answer = _message_text(reply)
            if getattr(reply, "tool_calls", None) or not answer.strip():
                return None
            problems = self._check_citations(answer, trace)
            if not problems or attempt == 1:
                self.riwayat.append(AIMessage(content=answer))
                return answer, problems
            messages += [AIMessage(content=answer),
                         HumanMessage(content=CITATION_NOTICE + "\n".join(f"- {m}" for m in problems))]
        return None

    def _named_regulations(self, question: str, trace: list[ToolCall]) -> list[str]:
        if "find_regulation" not in self._tools_by_name or os.environ.get("PPH21_ABLATION_SENSOR") == "0":
            return []
        from ..monitor.identity import find_all_query
        from ..tools.registry import report_possibly_stale
        from ..tools.regulation_graph import find_regulation

        unknown = []
        for ident in find_all_query((question or "").upper()):
            h = find_regulation(regulation=str(ident))
            if h.get("berhasil") or "tidak ada di graf" not in str(h.get("galat", "")):
                continue
            args = {"reason": "peraturan_tidak_dikenal", "regulation": str(ident),
                    "details": f"Pengguna menyebut {ident}; peraturan itu tidak ada di graf (pemeriksaan otomatis)."}
            result = {**report_possibly_stale(**args), "peraturan": [str(ident)]}
            trace.append(ToolCall(name="report_possibly_stale", arguments={**args, "otomatis": True}, result=result))
            unknown.append(str(ident))
        return unknown

    def _repealed_basis(self, result: Any, trace: list[ToolCall]) -> list[str]:
        from .stale_reports import NOT_IN_FORCE

        if not isinstance(result, dict):
            return []
        from ..tools.registry import report_possibly_stale

        found = []
        for st in result.get("status_dasar_hukum") or []:
            reg = st.get("peraturan")
            if not reg or st.get("status") not in NOT_IN_FORCE or reg in self._repealed + found:
                continue
            by = st.get("oleh")
            by = ", ".join(map(str, by)) if isinstance(by, list) else (by or "")
            args = {"reason": "dasar_hukum_tidak_berlaku", "regulation": reg, "fact_date": st.get("pada") or "",
                    "details": f"Dasar hukum hitungan {reg} berstatus {st['status']}"
                               + (f" oleh {by}" if by else "") + f" pada {st.get('pada')} (pemeriksaan otomatis)."}
            report = {**report_possibly_stale(**args), "peraturan": [reg]}
            trace.append(ToolCall(name="report_possibly_stale", arguments={**args, "otomatis": True}, result=report))
            found.append(reg)
        if found:
            result["peringatan_dasar_hukum"] = REPEALED_BASIS_NOTE.format(regs=", ".join(found))
        return found

    def _turn(self, answer: str, trace: list[ToolCall], rounds: int, corrections: list[str],
              problems: list[str] | None) -> AgentTurn:
        from ..monitor.identity import find_all_query

        named = {str(i) for i in find_all_query((answer or "").upper())}
        missing = [r for r in self._unknown if r not in named]
        repealed = list(dict.fromkeys(self._repealed))
        loose = self._unsourced_numbers(answer, trace)
        if loose:
            answer += NUMBER_NOTE.format(amounts=_rupiah(loose))
        if missing:
            answer += UNKNOWN_REGULATION_ANSWER.format(regs=", ".join(missing))
        unstated = list(getattr(self, "_unstated", []) or [])
        if unstated:
            from ..tools.regulation_graph import stamp_status

            answer = stamp_status(answer, unstated, getattr(self, "_status_date", None))
        if repealed:
            answer += REPEALED_BASIS_ANSWER.format(regs=", ".join(repealed))
        return AgentTurn(answer=mark_citations(answer, problems), trace=trace, rounds=rounds,
                         status_stamped=[k for k, _ in unstated],
                         citation_corrections=corrections, citation_unverified=list(problems or []),
                         citation_checked=problems is not None, citation_audit=list(self.citation_audit),
                         number_corrections=list(getattr(self, "_number_corrections", [])), numbers_unsourced=loose,
                         tokens_in=getattr(self, "tokens_in", 0), tokens_out=getattr(self, "tokens_out", 0))

    def _user_text(self) -> str:
        from langchain_core.messages import HumanMessage

        return "\n".join(_message_text(m) for m in self.riwayat if isinstance(m, HumanMessage)
                         and not _message_text(m).startswith(_NOTICES))

    def _unsourced_numbers(self, answer: str, trace: list[ToolCall]) -> list[int]:
        from .numbers import numbers_in, unsourced

        return unsourced(answer, numbers_in([j.result for j in trace]) | numbers_in(self._user_text()))

    def ask(self, question: str, on_tool: Callable[[str, str, dict, Any], None] | None = None) -> AgentTurn:
        from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

        def notify(stage: str, name: str, tool_args: dict, result: Any) -> None:
            if on_tool is None:
                return
            with contextlib.suppress(Exception):
                on_tool(stage, name, tool_args, result)

        self.riwayat.append(HumanMessage(content=question))
        trace: list[ToolCall] = []
        corrections: list[str] = []
        self.citation_audit = []
        self._unstated: list[tuple[str, dict]] = []
        self._number_corrections: list[int] = []
        self._repealed = []
        self._unknown = self._named_regulations(question, trace)
        if self._unknown:
            self.riwayat.append(SystemMessage(content=UNKNOWN_REGULATION_NOTE.format(regs=", ".join(self._unknown))))

        for turn in range(1, MAX_TURNS + 1):
            reply = self._invoke(self.riwayat)
            self.riwayat.append(reply)

            calls = getattr(reply, "tool_calls", None) or []
            if not calls:
                answer = _message_text(reply)
                problems = self._check_citations(answer, trace)
                if problems and not corrections:
                    corrections = problems
                    self.riwayat.append(HumanMessage(content=CITATION_NOTICE + "\n".join(f"- {m}" for m in problems)))
                    continue
                loose = self._unsourced_numbers(answer, trace)
                if loose and not self._number_corrections:
                    self._number_corrections = loose
                    self.riwayat.append(HumanMessage(content=NUMBER_NOTICE.format(amounts=_rupiah(loose))))
                    continue
                return self._turn(answer, trace, turn, corrections, problems)

            for tc in calls:
                name = tc["name"]
                tool_args = tc.get("args", {}) or {}
                if self.verbose:
                    print(f"  -> {name}({json.dumps(tool_args, ensure_ascii=False)})")

                notify("mulai", name, tool_args, None)
                tool = self._tools_by_name.get(name)
                user_text = self._user_text()
                rejected = (check_scope(name, question) or check_ptkp_status(name, tool_args, user_text, question)
                            if tool is not None else None)
                if rejected is not None:
                    result = rejected
                elif tool is None:
                    result = {
                        "berhasil": False,
                        "galat": f"tool '{name}' tidak ada",
                        "saran": f"Pilih salah satu dari: {list(self._tools_by_name)}",
                    }
                else:
                    try:
                        result = tool.invoke(tool_args)
                    except Exception as exc:  # noqa: BLE001
                        result = {
                            "berhasil": False,
                            "galat": f"{type(exc).__name__}: {exc}",
                            "saran": "Periksa nama dan tipe argumen, lalu panggil ulang.",
                        }

                trace.append(ToolCall(name=name, arguments=tool_args, result=result))
                self._repealed += self._repealed_basis(result, trace)
                notify("selesai", name, tool_args, result)
                self.riwayat.append(
                    ToolMessage(
                        content=json.dumps(result, ensure_ascii=False, default=str),
                        tool_call_id=tc.get("id", name),
                    )
                )

        final = self._answer_without_tools(trace)
        if final is not None:
            return self._turn(final[0], trace, MAX_TURNS + 1, corrections, final[1])
        return AgentTurn(
            citation_corrections=corrections,
            answer=(
                f"Berhenti setelah {MAX_TURNS} putaran tanpa jawaban akhir. "
                "Coba persempit pertanyaannya."
            ),
            trace=trace,
            rounds=MAX_TURNS,
            tokens_in=getattr(self, "tokens_in", 0),
            tokens_out=getattr(self, "tokens_out", 0),
        )


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def _is_guarded(tool_name: str) -> bool:
    return tool_name.startswith("calculate_pph") or tool_name == "lookup_ptkp"


def is_valid_quote(quote: str, user_text: str) -> bool:
    k = _normalize(quote).strip(" '\"`.,;:")
    return len(k) >= 2 and k in _normalize(user_text) and states_status(k)


_STATUS_WORDS = re.compile(r"ptkp|kawin|nikah|lajang|single|bujang|jomblo|janda|duda|cerai"
                           r"|istri|isteri|suami|anak|tanggungan|keluarga")
_PTKP_CODE = re.compile(r"(?<![a-z0-9])(tk|k)\s*([/.\-]\s*|\s+)?([0-3])(?![0-9a-z/])")
_STATUS_CONTEXT = re.compile(r"\b(?:status|ptkp)\b")


def ptkp_codes(quote: str) -> set[str]:
    q = _normalize(quote).strip(" '\"`.,;:")
    codes = set()
    for m in _PTKP_CODE.finditer(q):
        prefix, separator, n = m.group(1), m.group(2), m.group(3)
        if prefix == "k" and not separator and not (_STATUS_CONTEXT.search(q) or q == m.group(0)):
            continue
        codes.add(f"{prefix.upper()}/{n}")
    return codes


def states_status(quote: str) -> bool:
    return bool(ptkp_codes(quote)) or bool(_STATUS_WORDS.search(_normalize(quote)))


def _status_code(status: str) -> str:
    return "".join((status or "").upper().split())


def mentions_ki_status(user_text: str) -> bool:
    return "k/i/" in "".join((user_text or "").lower().split())


KI_STATUS_ERROR = {
    "berhasil": False,
    "galat": "Pengguna menyebut status PTKP K/I/... (penghasilan istri digabung dengan suami). "
             "Status ini tidak didukung kalkulator: PP 58/2023 hanya mendefinisikan TK/0-TK/3 dan K/0-K/3.",
    "saran": "Jangan mengganti K/I/... menjadi K/... atau status lain. Sampaikan kepada pengguna bahwa "
             "perhitungan ini tidak didukung dan jangan menghitung.",
}

PTKP_QUOTE_ERROR = {
    "berhasil": False,
    "galat": "kutipan_status_ptkp kosong, tidak ada persis di pesan pengguna, atau tidak menyebut status "
             "kawin/tanggungan: status PTKP tidak boleh ditebak.",
    "saran": "Isi kutipan_status_ptkp dengan potongan kalimat pengguna yang menyebut status kawin/tanggungan "
             "atau kode PTKP, disalin persis. Kalau pengguna belum menyebutnya, tanyakan status kawin dan "
             "jumlah tanggungan (boleh sekaligus dengan data lain yang kurang), sebagai pertanyaan baru tanpa "
             "menyebut galat ini.",
}

PTKP_CODE_MISMATCH = {
    "berhasil": False,
    "galat": "kutipan_status_ptkp menyebut kode {codes}, tetapi status_ptkp diisi {chosen}.",
    "saran": "Pakai status PTKP yang disebut pengguna. Kalau pengguna menyebut lebih dari satu status dan tidak jelas "
             "mana yang berlaku, tanyakan.",
}


_OTHER_TAX = re.compile(
    r"\bpph\s*badan\b|pajak penghasilan badan|\bppn\s*bm\b|\bppnbm\b|\bppn\b|pajak pertambahan nilai|\bpbb\b"
    r"|pajak bumi|\bbphtb\b|bea m[ae]terai|\bpph\s*(?:pasal\s*)?(?:4\s*(?:ayat\s*)?\(?2\)?|15|22|23|25|29)(?!\d)"
    r"|pajak penghasilan pasal (?:4 ayat \(?2\)?|15|22|23|25|29)(?!\d)")
_OWN_TAX = re.compile(r"\bpph\s*(?:pasal\s*)?2[16](?!\d)|pajak penghasilan pasal 2[16](?!\d)")


def names_other_tax(message: str) -> bool:
    text = _normalize(message)
    return bool(_OTHER_TAX.search(text)) and not _OWN_TAX.search(text)


OUT_OF_SCOPE_ERROR = {
    "berhasil": False,
    "galat": "Pertanyaan menyebut jenis pajak lain (bukan PPh 21/26). Kalkulator ini hanya menghitung PPh 21 dan "
             "PPh 26, jadi hasilnya tidak menjawab pertanyaan itu.",
    "saran": "Jangan menghitung dengan tool PPh 21/26 dan jangan menghitung sendiri. Katakan bahwa jenis pajak ini di "
             "luar cakupan; boleh menjelaskan dasar hukumnya tanpa angka hasil hitung.",
}


def check_scope(tool_name: str, last_message: str) -> dict | None:
    if tool_name.startswith("calculate_") and names_other_tax(last_message):
        return dict(OUT_OF_SCOPE_ERROR)
    return None


def check_ptkp_status(tool_name: str, tool_args: dict, user_text: str, last_message: str) -> dict | None:
    if not _is_guarded(tool_name):
        return None
    if mentions_ki_status(last_message):
        return dict(KI_STATUS_ERROR)
    states_status = tool_name == "lookup_ptkp" or (tool_args.get("status_ptkp") or "").strip()
    quote = tool_args.get("kutipan_status_ptkp", "")
    if states_status and not is_valid_quote(quote, user_text):
        return dict(PTKP_QUOTE_ERROR)
    codes, chosen = ptkp_codes(quote), _status_code(tool_args.get("status_ptkp", ""))
    if codes and chosen and chosen not in codes:
        return {**PTKP_CODE_MISMATCH, "galat": PTKP_CODE_MISMATCH["galat"].format(
            codes=", ".join(sorted(codes)), chosen=chosen)}
    return None


def _message_text(messages) -> str:
    content = getattr(messages, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, Iterable):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(b for b in parts if b)
    return str(content)  # pragma: no cover
