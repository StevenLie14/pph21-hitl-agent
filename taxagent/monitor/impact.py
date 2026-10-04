from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..paths import TESTS_DIR
from ..settings import get_settings
from ..taxes import get as tax_module
from .classify import Watchlist, classify, load_watchlist
from .classify_llm import LLMCache, excerpt, round_robin_spans
from .identity import RegulationId
from .text import extract

DATA_DIR = tax_module().data_dir

GRAPH_FILE = DATA_DIR / "graf_dampak.yaml"
LABELS_FILE = DATA_DIR / "dampak_label.yaml"
CORE_DIR = tax_module().calc_dir
TESTS_DIR = TESTS_DIR


@dataclass
class ImpactGraph:
    parameters: dict[str, dict]
    regulations: dict[RegulationId, list[str]]
    functions: dict[str, set[str]]
    tests: dict[str, set[str]] = field(default_factory=dict)
    regulation_articles: dict[RegulationId, dict[str, list[str]]] = field(default_factory=dict)

    def without(self, ident: RegulationId | None) -> ImpactGraph:
        if ident is None or ident not in self.regulations:
            return self
        return ImpactGraph(self.parameters, {k: v for k, v in self.regulations.items() if k != ident}, self.functions, self.tests,
                    {k: v for k, v in self.regulation_articles.items() if k != ident})

    def relation_keys(self, ident: RegulationId, articles: list[str] | None = None) -> tuple[list[str], str]:
        article_map = self.regulation_articles.get(ident)
        if not (article_map and articles):
            return list(self.regulations.get(ident, [])), ""
        keys, hit = [], []
        for p in articles:
            ks = article_map.get(p) or article_map.get(re.sub(r"[A-Z]+$", "", p)) or []
            if ks:
                hit.append(p)
            keys += [k for k in ks if k in self.parameters and k not in keys]
        return keys, f"pasal diubah {', '.join(articles)}; berdampak: {', '.join(hit) or 'tidak ada'}"

    def descendants(self, keys: set[str]) -> set[str]:
        result, queue = set(), list(keys)
        while queue:
            k = queue.pop()
            for t in self.parameters.get(k, {}).get("masukan_ke", []) or []:
                if t not in result and t not in keys:
                    result.add(t)
                    queue.append(t)
        return result

    def affected_functions(self, keys: set[str]) -> set[str]:
        return {f for f, ks in self.functions.items() if ks & keys}

    def affected_tests(self, functions: set[str]) -> set[str]:
        return {t for f in functions for t in self.tests.get(f, set())}

    def definers(self, key: str) -> list[str]:
        return sorted(str(i) for i, ks in self.regulations.items() if key in ks)


def build_graph(wl: Watchlist | None = None, path: Path | None = None) -> ImpactGraph:
    data = yaml.safe_load(Path(path or GRAPH_FILE).read_text(encoding="utf-8"))
    parameter = data["parameter"]
    wl = wl or load_watchlist()
    regulations = {
        e.identity: [k for k in e.governs if k in parameter]
        for e in wl.regulations if e.role == "dasar"
    }
    attr_map = data.get("atribut_kode", {})
    module_params = data.get("modul_parameter", {})
    functions: dict[str, set[str]] = {}
    for f in sorted(CORE_DIR.glob("*.py")):
        source = f.read_text(encoding="utf-8")
        names = re.findall(r"^def (calc_[a-z0-9_]+)", source, re.M)
        if not names:
            continue
        keys = {attr_map[a] for a in re.findall(r"\btable\.([a-z_0-9]+)", source) if a in attr_map}
        keys |= set(module_params.get(f.name, []))
        keys.add("mekanisme_pemotongan")
        for n in names:
            functions[n] = set(keys)
    test: dict[str, set[str]] = {}
    if TESTS_DIR.exists():
        contents = {t.name: t.read_text(encoding="utf-8", errors="ignore") for t in TESTS_DIR.glob("test_*.py")}
        for n in functions:
            pattern = re.compile(rf"\b{n}\b")
            test[n] = {t for t, s in contents.items() if pattern.search(s)}
    regulation_articles = {
        e.identity: {p: [k for k in ks if k in parameter] for p, ks in e.governed_articles}
        for e in wl.regulations if e.role == "dasar" and e.governed_articles
    }
    return ImpactGraph(parameter, regulations, functions, test, regulation_articles)


def text_relations(text: str, ident: RegulationId | None) -> list[tuple[str, RegulationId, list[str] | None]]:
    e = extract(text, ident)
    result = [("mencabut_sebagian" if p.sebagian else "mencabut", p.identitas, None) for p in e.revokes]
    result += [("mengubah", i, e.amended_articles.get(i)) for i in e.amends if i not in e.amends_intermediate]
    return result


@dataclass
class ImpactResult:
    keys: set[str]
    reasons: list[str] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    seconds: float = 0.0
    local_seconds: float = 0.0
    dropped_quotes: list[str] = field(default_factory=list)
    unknown_keys: list[str] = field(default_factory=list)
    from_relations: set[str] = field(default_factory=set)
    derived: set[str] = field(default_factory=set)
    functions: set[str] = field(default_factory=set)
    tests: set[str] = field(default_factory=set)
    valid: bool = True
    llm_called: bool = False
    candidates: list[str] = field(default_factory=list)


def _relation_keys(relations, graph: ImpactGraph) -> tuple[set[str], list[str]]:
    keys, alasan = set(), []
    for kind, i, articles in relations:
        ks, note = graph.relation_keys(i, articles)
        if ks or note:
            keys |= set(ks)
            alasan.append(f"{kind} {i}{f' ({note})' if note else ''} -> {', '.join(ks) or '-'}")
    return keys, alasan


def rule_impact(title: str, subject: str, ident: RegulationId | None, text: str, wl: Watchlist, graph: ImpactGraph) -> ImpactResult:
    t0 = time.perf_counter()
    k = classify(title, subject, ident, wl)
    keys = {x for x in k.affected_keys if x in graph.parameters}
    alasan = [f"klasifikasi: {'; '.join(k.reasons)}"] if k.reasons else []
    kr, ar = _relation_keys(text_relations(text, ident), graph)
    if k.category == "fasilitas":
        keys, kr = set(), set()
    keys |= kr
    dt = time.perf_counter() - t0
    return ImpactResult(keys, alasan + ar, seconds=dt, local_seconds=dt, from_relations=kr)


_LABEL_RULES = """\
Sebutkan key yang angka atau logika hitungnya DIATUR LANGSUNG oleh peraturan ini. Bukan dampak \
turunan. Peraturan fasilitas (PPh 21 ditanggung pemerintah, insentif, pembebasan) tidak pernah \
mengubah tarif, PTKP, atau TER: kosongkan. Peraturan prosedural (bukti potong, SPT Masa, \
administrasi) tidak mengubah angka maupun logika hitung: kosongkan. Peraturan yang tidak \
berhubungan dengan PPh 21: kosongkan. Jika teks mengatur sesuatu yang dipakai dalam hitungan \
PPh 21 (tarif, pengurang penghasilan, objek penghasilan pegawai, batas), sertakan key-nya walau \
peraturan itu juga mengatur hal lain: reviewer akan memeriksa, dan melewatkan dampak lebih mahal \
daripada satu key yang ternyata tidak perlu."""

IMPACT_PROMPT_VERSION = "dampak-v2-2026-10-06"


def graph_excerpt(text: str, graph: ImpactGraph, limit: int = 6000, head: int = 1000, window: int = 400) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    if len(t) <= limit:
        return t
    lower = t.lower()
    per_key: list[list[int]] = []
    for p in graph.parameters.values():
        positions = sorted({m.start() for s in p.get("istilah", []) for m in re.finditer(re.escape(s.lower()), lower)
                         if m.start() >= head})
        if positions:
            per_key.append(positions)
    return round_robin_spans(t, per_key, limit, head, window)


def _quote_present(quote: str, norm_text: str) -> bool:
    pieces = [_norm(x) for x in re.split(r"\.{3,}|…|\[\.\.\.\]", quote or "")]
    pieces = [x for x in pieces if x]
    return bool(pieces) and all(len(x) >= 10 and x in norm_text for x in pieces)


def _key_quote_pairs(data: dict) -> list[tuple[object, str]]:
    keys = data.get("key")
    if not isinstance(keys, list):
        return []
    quote = data.get("kutipan")
    result = []
    for n, x in enumerate(keys):
        if isinstance(x, dict):
            result.append((x.get("key"), str(x.get("kutipan", ""))))
        elif isinstance(quote, list) and n < len(quote):
            result.append((x, str(quote[n])))
        else:
            result.append((x, ""))
    return result


def _catalog(graph: ImpactGraph, with_graph: bool, keys: list[str] | None = None) -> str:
    lines = []
    for key, p in graph.parameters.items():
        if keys is not None and key not in keys:
            continue
        b = f"- {key}: {p['deskripsi']}"
        if with_graph:
            defined_by = graph.definers(key)
            fs = sorted(f for f, ks in graph.functions.items() if key in ks)
            b += f" | didefinisikan oleh: {', '.join(defined_by) or '-'} | dipakai: {len(fs)} fungsi hitung"
        lines.append(b)
    return "\n".join(lines)


def llm_prompt(graph: ImpactGraph) -> str:
    return (
        "Anda memelihara kalkulator PPh Pasal 21 di Indonesia. Diberi cuplikan teks peraturan dan "
        "katalog key data kalkulator.\n\n" + _LABEL_RULES + "\n\nKatalog key:\n" + _catalog(graph, False)
        + '\n\nJawab HANYA JSON: {"key": ["..."], "alasan": "satu kalimat"}'
    )


def candidates_from_text(text: str, graph: ImpactGraph) -> list[str]:
    lower = re.sub(r"\s+", " ", (text or "").lower())
    return [k for k, p in graph.parameters.items() if any(s.lower() in lower for s in p.get("istilah", []))]


def graph_llm_prompt(graph: ImpactGraph, keys: list[str] | None = None) -> str:
    return (
        "Anda memelihara kalkulator PPh Pasal 21 di Indonesia. Diberi cuplikan teks peraturan, "
        "katalog key data kalkulator beserta peraturan yang saat ini mendefinisikannya (dari graf), "
        "dan fakta graf tentang peraturan yang dicabut/diubah oleh dokumen ini.\n\n" + _LABEL_RULES
        + " Untuk SETIAP key, sertakan kutipan VERBATIM pendek (5-25 kata) dari cuplikan yang menunjukkan "
        "pengaturannya, disalin persis tanpa \"...\"; key tanpa kutipan yang ada persis di teks akan dibuang."
        + ("\n\nKatalog key (hanya key yang istilahnya muncul di dokumen ini):\n" if keys is not None else "\n\nKatalog key:\n")
        + _catalog(graph, True, keys)
        + '\n\nJawab HANYA JSON: {"key": [{"key": "...", "kutipan": "..."}], "alasan": "satu kalimat"}'
    )


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w%]+", " ", (s or "").lower())).strip()


def _json(raw: str) -> dict | None:
    m = re.search(r"\{.*\}", raw or "", re.S)
    try:
        d = json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        return None
    return d if isinstance(d, dict) else None


@dataclass
class MeteredClient:
    call: object
    model_id: str
    cache: LLMCache
    attempts: int = 3

    def __call__(self, system: str, user: str, version: str) -> tuple[dict | None, dict]:
        key = LLMCache.make_key(self.model_id, 0, user, system, version)
        cached = self.cache.get(key)
        if cached is None:
            error = None
            for i in range(self.attempts):
                try:
                    t0 = time.perf_counter()
                    r = self.call(system, user)
                    cached = {
                        "kunci": key, "model": self.model_id, "prompt_versi": version, "ulangan": 0,
                        "mentah": r["teks"], "token_masuk": r.get("token_masuk", 0),
                        "token_keluar": r.get("token_keluar", 0), "detik": time.perf_counter() - t0,
                    }
                    self.cache.put(cached)
                    break
                except Exception as exc:  # noqa: BLE001
                    error = exc
                    if i + 1 < self.attempts:
                        time.sleep(min(30.0, 2.0 * 2 ** i))
            if cached is None:
                return None, {"galat": str(error)}
        return _json(cached["mentah"]), cached


def llm_impact(title: str, ident: RegulationId | None, text: str, client: MeteredClient, graph: ImpactGraph) -> ImpactResult:
    user = f"Jenis dan nomor: {ident or '-'}\nJudul: {title}\nCuplikan teks:\n{excerpt(text)}"
    data, record = client(llm_prompt(graph), user, IMPACT_PROMPT_VERSION)
    h = ImpactResult(set(), tokens_in=record.get("token_masuk", 0), tokens_out=record.get("token_keluar", 0),
                    seconds=record.get("detik", 0.0), llm_called=True)
    if data is None or not isinstance(data.get("key"), list):
        h.valid = False
        h.reasons = [f"jawaban LLM tidak valid: {record.get('galat') or (record.get('mentah') or '')[:120]}"]
        return h
    for x in data["key"]:
        k = x.get("key") if isinstance(x, dict) else x
        if isinstance(k, str) and k in graph.parameters:
            h.keys.add(k)
        else:
            h.unknown_keys.append(str(k))
    h.reasons = [str(data.get("alasan", ""))]
    return h


def _graph_facts(graph: ImpactGraph, ident: RegulationId, articles: list[str] | None) -> str:
    if ident not in graph.regulations:
        return " (tidak ada di graf)"
    ks, note = graph.relation_keys(ident, articles)
    if note:
        return f" ({note}; key: {', '.join(ks) or 'tidak ada'})"
    return f" (mendefinisikan: {', '.join(ks)})"


def graph_llm_impact(title: str, ident: RegulationId | None, text: str, client: MeteredClient, graph: ImpactGraph,
                    filtered: bool = False, full_text: bool = False) -> ImpactResult:
    t0 = time.perf_counter()
    relations = text_relations(text, ident)
    kr, ar = _relation_keys(relations, graph)
    facts = [f"dokumen ini {j.replace('_', ' ')} {i}" + _graph_facts(graph, i, p) for j, i, p in relations]
    candidates = candidates_from_text(text, graph) if filtered else None
    excerpt_graph = graph if candidates is None else ImpactGraph({k: graph.parameters[k] for k in candidates}, graph.regulations, graph.functions, graph.tests, graph.regulation_articles)
    local_s = time.perf_counter() - t0
    if candidates is not None and not candidates:
        h = ImpactResult(set(kr), list(ar) + ["tidak ada istilah parameter di teks: LLM tidak dipanggil"],
                        from_relations=set(kr))
        h.derived = graph.descendants(h.keys)
        h.functions = graph.affected_functions(h.keys | h.derived)
        h.tests = graph.affected_tests(h.functions)
        h.seconds = h.local_seconds = time.perf_counter() - t0
        return h
    user = (
        f"Jenis dan nomor: {ident or '-'}\nJudul: {title}\nFakta graf: {'; '.join(facts) or 'tidak ada relasi ke peraturan lain'}\n"
        + ("Teks lengkap:\n" + re.sub(r"\s+", " ", text or "").strip() if full_text else
           f"Cuplikan teks (dipilih di sekitar istilah setiap parameter graf):\n{graph_excerpt(text, excerpt_graph)}")
    )
    version = IMPACT_PROMPT_VERSION + ("-graf-saring" if filtered else "-graf") + ("-utuh" if full_text else "")
    data, record = client(graph_llm_prompt(graph, candidates), user, version)
    t1 = time.perf_counter()
    h = ImpactResult(set(kr), list(ar), record.get("token_masuk", 0), record.get("token_keluar", 0), from_relations=set(kr),
                    llm_called=True, candidates=candidates or [])
    if data is None or not isinstance(data.get("key"), list):
        h.valid = False
        h.reasons.append(f"jawaban LLM tidak valid: {record.get('galat') or (record.get('mentah') or '')[:120]}")
    else:
        norm_text = _norm(text)
        for k, quote in _key_quote_pairs(data):
            if not isinstance(k, str) or k not in graph.parameters:
                h.unknown_keys.append(str(k))
            elif _quote_present(quote, norm_text):
                h.keys.add(k)
            else:
                h.dropped_quotes.append(k)
        h.reasons.append(str(data.get("alasan", "")))
    h.derived = graph.descendants(h.keys)
    h.functions = graph.affected_functions(h.keys | h.derived)
    h.tests = graph.affected_tests(h.functions)
    local_s += time.perf_counter() - t1
    h.local_seconds = local_s
    h.seconds = record.get("detik", 0.0) + local_s
    return h


def cascade_impact(title: str, subject: str, ident: RegulationId | None, text: str, wl: Watchlist,
                   client: MeteredClient, graph: ImpactGraph) -> ImpactResult:
    a = rule_impact(title, subject, ident, text, wl, graph)
    if a.keys:
        a.reasons.insert(0, "kaskade: selesai di aturan, LLM tidak dipanggil")
        a.derived = graph.descendants(a.keys)
        a.functions = graph.affected_functions(a.keys | a.derived)
        a.tests = graph.affected_tests(a.functions)
        return a
    h = graph_llm_impact(title, ident, text, client, graph, filtered=True)
    h.reasons.insert(0, "kaskade: aturan tidak menemukan key")
    h.seconds += a.seconds
    h.local_seconds += a.local_seconds
    return h


MAX_TEXT_CHARS = 200_000
_RE_CHAPTER = re.compile(r"(?=\bBAB\s+[IVXLC]+\b)")


def chapters(text: str, limit: int = MAX_TEXT_CHARS) -> list[str]:
    t = re.sub(r"\s+", " ", text or "").strip()
    if len(t) <= limit:
        return [t]
    parts, current = [], ""
    for chunk in (p for p in _RE_CHAPTER.split(t) if p):
        while len(chunk) > limit:
            if current:
                parts.append(current)
                current = ""
            parts.append(chunk[:limit])
            chunk = chunk[limit:]
        if len(current) + len(chunk) > limit:
            parts.append(current)
            current = ""
        current += chunk
    if current:
        parts.append(current)
    return parts


def union_impact(title: str, subject: str, ident: RegulationId | None, text: str, wl: Watchlist,
                 client: MeteredClient, graph: ImpactGraph, limit: int = MAX_TEXT_CHARS) -> ImpactResult:
    a = rule_impact(title, subject, ident, text, wl, graph)
    h = ImpactResult(set(a.keys), ["gabungan: kunci aturan + LLM teks utuh"] + list(a.reasons),
                     seconds=a.seconds, local_seconds=a.local_seconds, from_relations=set(a.from_relations))
    pieces = chapters(text, limit)
    for n, piece in enumerate(pieces, 1):
        r = graph_llm_impact(title, ident, piece, client, graph, filtered=True, full_text=True)
        h.keys |= r.keys
        h.from_relations |= r.from_relations
        h.tokens_in += r.tokens_in
        h.tokens_out += r.tokens_out
        h.seconds += r.seconds
        h.local_seconds += r.local_seconds
        h.dropped_quotes += r.dropped_quotes
        h.unknown_keys += r.unknown_keys
        h.valid = h.valid and r.valid
        h.llm_called = h.llm_called or r.llm_called
        h.candidates = sorted(set(h.candidates) | set(r.candidates))
        prefix = f"bagian {n}/{len(pieces)}: " if len(pieces) > 1 else "LLM: "
        h.reasons += [prefix + x for x in r.reasons if x]
    h.derived = graph.descendants(h.keys)
    h.functions = graph.affected_functions(h.keys | h.derived)
    h.tests = graph.affected_tests(h.functions)
    return h


def monitor_impact(title: str, subject: str, ident: RegulationId | None, text: str, wl: Watchlist, graph: ImpactGraph,
                    client: MeteredClient | None = None, facility: bool = False) -> dict:
    if facility:
        return {"keys": [], "turunan": [], "fungsi": [], "test": [], "sumber": "gerbang_fasilitas",
                "alasan": ["fasilitas (mis. PPh 21 DTP) tidak mengubah tarif/PTKP/TER: tidak diberi key"]}
    if client is None:
        h = rule_impact(title, subject, ident, text, wl, graph)
        h.derived = graph.descendants(h.keys)
        h.functions = graph.affected_functions(h.keys | h.derived)
        h.tests = graph.affected_tests(h.functions)
        source = "graf"
    else:
        h = union_impact(title, subject, ident, text, wl, client, graph)
        source = "gabungan" if h.llm_called else "graf"
    return {
        "keys": sorted(h.keys), "turunan": sorted(h.derived), "fungsi": sorted(h.functions), "test": sorted(h.tests),
        "sumber": source, "alasan": [a for a in h.reasons if a], "dari_relasi": sorted(h.from_relations),
        "dibuang_kutipan": h.dropped_quotes, "valid": h.valid,
        "token": h.tokens_in + h.tokens_out,
    }


def metered_langchain_call(provider: str | None = None, model: str | None = None):
    from ..agent.runner import build_model, default_provider

    provider = (provider or default_provider()).lower()
    m = build_model(model=model, temperature=0.0, provider=provider)
    if provider in ("azure", "openai"):
        m = m.bind(response_format={"type": "json_object"})
    name = model or (get_settings().azure_deployment if provider == "azure" else None) or "default"

    def call(system: str, user: str) -> dict:
        from langchain_core.messages import HumanMessage, SystemMessage

        r = m.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        u = getattr(r, "usage_metadata", None) or {}
        content = r.content if isinstance(r.content, str) else "".join(
            x.get("text", "") if isinstance(x, dict) else str(x) for x in r.content
        )
        return {"teks": content, "token_masuk": u.get("input_tokens", 0), "token_keluar": u.get("output_tokens", 0)}

    return call, f"{provider}:{name}"


def load_labels(path: Path | None = None) -> dict[str, dict]:
    data = yaml.safe_load(Path(path or LABELS_FILE).read_text(encoding="utf-8"))
    return data.get("dasar", {})


@dataclass
class ImpactScore:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    exact: int = 0
    n: int = 0
    violations: int = 0

    @property
    def precision(self):
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else None

    @property
    def recall(self):
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else None

    @property
    def f1(self):
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p and r else None


def score(predicted: dict[str, set[str]], label: dict[str, set[str]], non_base: set[str]) -> tuple[ImpactScore, ImpactScore]:
    d, nd = ImpactScore(), ImpactScore()
    for i, expected in label.items():
        p = predicted.get(i, set())
        d.n += 1
        d.tp += len(p & expected)
        d.fp += len(p - expected)
        d.fn += len(expected - p)
        d.exact += p == expected
    for i in non_base:
        p = predicted.get(i, set())
        nd.n += 1
        nd.fp += len(p)
        nd.violations += bool(p)
        nd.exact += not p
    return d, nd
