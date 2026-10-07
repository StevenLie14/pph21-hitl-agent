from __future__ import annotations

import logging
import re
from decimal import Decimal

from ..tools import regulation_graph as G
from .amounts import clean_text, yaml_number
from .extraction import ExtractionResult, Finding
from .llm import GROUPS, PROMPT_VERSION, LLMResult, group_field_pattern, groups_in_text, parse, system_prompt
from .manifest import load

log = logging.getLogger(__name__)

GRAPH_PROMPT_VERSION = PROMPT_VERSION + "+graf"
_BRACKET = tuple(k for k, g in load().groups.items() if g.layered)


IMPACT_TYPES = ("mengubah", "mencabut", "mencabut_sebagian")


def keys_from_graph(doc_key: str) -> tuple[list[str], list[str]]:
    chain = G.amendment_chain(regulation=doc_key)
    if not chain.get("berhasil"):
        return [], [f"rantai tidak tersedia: {chain.get('galat')}"]
    keys, trace = [], []
    for e in chain["mengubah_atau_mencabut"]:
        if e["jenis"] not in IMPACT_TYPES:
            continue
        for d in G.parameters_defined_by(e["peraturan"]):
            rel_articles = {re.sub(r"\(.*", "", p) for p in e.get("pasal_terdampak") or []}
            def_articles = set(d.get("pasal") or [])
            if e["jenis"] != "mencabut" and rel_articles and def_articles and not (rel_articles & def_articles):
                continue
            if d["nama"] not in keys:
                keys.append(d["nama"])
                shared = rel_articles & def_articles
                trace.append(f"{e['jenis']} {e['peraturan']} ({e.get('bukti')})"
                             + (f" Pasal {', '.join(sorted(shared))}" if shared else "")
                             + f" -> {d['nama']}")
    return keys, trace


def _groups(keys: list[str]) -> list[str]:
    return [k for k in GROUPS if k in keys]


def evidence(doc_key: str, group: str, max_chars: int = 6000) -> str:
    terms = GROUPS[group][0]
    query = " OR ".join(f'"{s}"' for s in terms)
    try:
        hits = G.top_chunks(doc_key, query)
    except Exception:  # noqa: BLE001
        log.warning("graph evidence for %s unavailable", doc_key, exc_info=True)
        return ""
    chunks, total = [], 0
    for x in hits:
        text = x["teks"][:2500]
        if total + len(text) > max_chars:
            break
        chunks.append(text)
        total += len(text)
    return " [...] ".join(chunks)


def extract_with_graph(doc_key: str, doc_text: str, client, groups: list[str]) -> LLMResult:
    h = LLMResult(group=list(groups))
    for g in groups:
        excerpt = evidence(doc_key, g)
        if not excerpt:
            continue
        data, record = client(system_prompt(g), "Cuplikan teks peraturan (dari graf):\n" + excerpt,
                              GRAPH_PROMPT_VERSION)
        h.tokens += int(record.get("token_masuk", 0)) + int(record.get("token_keluar", 0))
        if data is None:
            h.valid = False
            h.error = (h.error + "; " if h.error else "") + f"{g}: {record.get('galat') or 'jawaban tidak bisa di-parse'}"
            continue
        parse(data, doc_text, group_field_pattern(g), h)
    return h


def to_extraction_result(h: LLMResult, text: str, source: str = "llm_graf") -> ExtractionResult:
    b = clean_text(text)
    result = ExtractionResult(mismatches=list(b.mismatches), verified=set(b.verified),
                              without_words=set(b.without_words))
    per_key: dict[str, dict[str, Decimal | None]] = {}
    for path, v in h.values.items():
        key = path.split(".")[0].split("[")[0]
        per_key.setdefault(key, {})[path] = v
    for key, leaves in per_key.items():
        quote = " | ".join(dict.fromkeys(h.quotes[j] for j in leaves if h.quotes.get(j)))
        if key in _BRACKET:
            idx = sorted({int(j.split("[")[1].split("]")[0]) for j in leaves})
            rows = []
            for i in idx:
                upper, rate = leaves.get(f"{key}[{i}].batas_atas", "x"), leaves.get(f"{key}[{i}].persen")
                if upper == "x" or rate is None:
                    rows = None
                    break
                rows.append({"batas_atas": None if upper is None else yaml_number(upper), "persen": yaml_number(rate)})
            if not rows or idx != list(range(len(idx))) or rows[-1]["batas_atas"] is not None:
                result.notes.append(f"{key}: lapisan dari LLM tidak lengkap/bersambung, tidak dipakai")
                continue
            result.findings.append(Finding(key, rows, quote, source))
        else:
            values = {j.split(".", 1)[1]: (None if v is None else yaml_number(v)) for j, v in leaves.items()}
            result.findings.append(Finding(key, values, quote, source))
    return result


def proposals(doc_key: str, doc_text: str, client,
              keys_fase1: list[str] | None = None) -> tuple[ExtractionResult, LLMResult, dict]:
    graph_keys, trace = keys_from_graph(doc_key)
    keys = list(dict.fromkeys((keys_fase1 or []) + graph_keys))
    groups = _groups(keys) or groups_in_text(doc_text)
    h = extract_with_graph(doc_key, doc_text, client, groups)
    return to_extraction_result(h, doc_text), h, {"keys_graf": graph_keys, "jejak": trace, "kelompok": groups}
