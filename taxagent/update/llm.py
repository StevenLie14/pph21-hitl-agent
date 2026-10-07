from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from .amounts import parse_rupiah
from .manifest import Manifest, load

PROMPT_VERSION = "draf-llm-v3-2026-11-16-teks-utuh"

FULL_TEXT_CHARS = 200_000

GROUPS: dict[str, tuple[tuple[str, ...], str]] = {k: (g.terms, g.catalog()) for k, g in load().groups.items()
                                                    if g.catalog()}

_PROMPT = """\
{pembuka} dari teks peraturan perundang-undangan \
Indonesia untuk diperiksa silang dengan ekstraktor lain. Ambil hanya angka yang DITETAPKAN di \
teks sebagai ketentuan untuk field berikut. Jangan menebak, menghitung, atau memakai pengetahuan \
Anda tentang nilai yang berlaku; field yang tidak tertulis di teks jangan dijawab.

Abaikan: angka dalam contoh penghitungan, ilustrasi, atau penjelasan (mis. "Contoh", "x Rp", hasil \
perkalian); angka untuk rezim atau kelompok lain walau mirip (mis. tarif final khusus, batas \
peredaran bruto, batas bulanan bila field menanyakan batas harian). Satu kalimat sering memuat \
beberapa field (persen, paling banyak setahun, paling banyak sebulan): laporkan semuanya.

Field:
{katalog}

Aturan nilai: rupiah sebagai bilangan bulat tanpa pemisah (Rp54.000.000,00 -> 54000000); persen \
sebagai bilangan (5% -> 5, 0,5% -> 0.5); null hanya untuk batas_atas lapisan teratas. Untuk setiap \
butir sertakan "kutipan": potongan VERBATIM 5-30 kata dari teks yang memuat angka itu, disalin \
persis tanpa "..."; butir yang kutipannya tidak ada persis di teks akan dibuang. Kutipan boleh sama \
untuk beberapa butir.

Jawab HANYA JSON: {{"nilai": [{{"field": "...", "nilai": 0, "kutipan": "..."}}]}}"""


def system_prompt(group: str, m: Manifest | None = None) -> str:
    m = m or load()
    return _PROMPT.format(pembuka=m.opening_prompt, katalog=m.groups[group].catalog())


def group_field_pattern(group: str, m: Manifest | None = None) -> re.Pattern:
    return (m or load()).groups[group].field_pattern()


def groups_in_text(text: str, m: Manifest | None = None) -> list[str]:
    lower = re.sub(r"\s+", " ", (text or "").lower())
    return [k for k, g in (m or load()).groups.items() if g.catalog() and any(s in lower for s in g.terms)]


def excerpt(text: str, terms: tuple[str, ...], limit: int = 6000, head: int = 300, window: int = 600) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    if len(t) <= limit:
        return t
    lower = t.lower()
    positions = sorted({m.start() for s in terms for m in re.finditer(re.escape(s), lower)})
    spans, budget = [(0, head)], limit - head
    for p in positions:
        if budget <= 0:
            break
        a, b = max(0, p - window), min(len(t), p + window)
        if a < spans[-1][1]:
            a = spans[-1][1]
            if a >= b:
                continue
            b = min(b, a + budget)
            spans[-1] = (spans[-1][0], b)
        else:
            b = min(b, a + budget)
            spans.append((a, b))
        budget -= b - a
    return " [...] ".join(t[a:b] for a, b in spans)


def pieces(text: str, terms: tuple[str, ...]) -> list[str]:
    from ..monitor.impact import chapters

    parts = chapters(text, FULL_TEXT_CHARS)
    if len(parts) == 1:
        return parts
    return [x for x in parts if any(s in x.lower() for s in terms)] or parts[:1]


@dataclass
class LLMResult:
    values: dict[str, Decimal | None] = field(default_factory=dict)
    quotes: dict[str, str] = field(default_factory=dict)
    dropped: list[str] = field(default_factory=list)
    valid: bool = True
    error: str = ""
    tokens: int = 0
    group: list[str] = field(default_factory=list)


def combine_llm(a: LLMResult | None, b: LLMResult | None) -> LLMResult | None:
    if a is None or b is None:
        return a if b is None else b
    out = LLMResult(dict(a.values), dict(a.quotes), list(a.dropped) + list(b.dropped), a.valid and b.valid,
                    "; ".join(x for x in (a.error, b.error) if x), a.tokens + b.tokens, list(a.group) + list(b.group))
    for k, v in b.values.items():
        if k in out.values and out.values[k] != v:
            out.dropped.append(f"{k}: sumber berbeda ({out.values[k]} dan {v})")
            out.values.pop(k)
        else:
            out.values.setdefault(k, v)
            if k in b.quotes:
                out.quotes.setdefault(k, b.quotes[k])
    return out


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w%,.]+", " ", (s or "").lower())).strip()


def _numbers_in(quote: str) -> set[Decimal]:
    result = set()
    for m in re.findall(r"\d[\d.,]*\d|\d", quote or ""):
        try:
            result.add(parse_rupiah(m.rstrip(".,")))
        except (InvalidOperation, ValueError):
            continue
    return result


def _decimal(v) -> Decimal | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        return Decimal(str(v).replace(",", "."))
    except InvalidOperation:
        return None


def parse(data: dict | None, text: str, pattern: re.Pattern | None = None, h: LLMResult | None = None) -> LLMResult:
    h = h or LLMResult()
    if not isinstance(data, dict) or not isinstance(data.get("nilai"), list):
        h.valid = False
        h.error = (h.error + "; " if h.error else "") + "jawaban bukan JSON {\"nilai\": [...]}"
        return h
    text_n = _norm(text)
    conflicts: set[str] = set()
    for b in data["nilai"]:
        if not isinstance(b, dict):
            continue
        f, quote = str(b.get("field", "")), str(b.get("kutipan", ""))
        if pattern is not None and not pattern.match(f):
            h.dropped.append(f"{f}: field tidak dikenal untuk kelompok ini")
            continue
        v = _decimal(b.get("nilai"))
        if v is None and not (b.get("nilai") is None and f.endswith(".batas_atas")):
            h.dropped.append(f"{f}: nilai tidak terbaca ({b.get('nilai')!r})")
            continue
        kn = _norm(quote)
        if len(kn) < 10 or kn not in text_n:
            h.dropped.append(f"{f}: kutipan tidak ada verbatim di teks")
            continue
        if v is not None and v not in _numbers_in(quote):
            h.dropped.append(f"{f}: angka {v} tidak ada di kutipan")
            continue
        if f in h.values and h.values[f] != v:
            h.dropped.append(f"{f}: dua jawaban berbeda ({h.values[f]} dan {v}), keduanya dibuang")
            conflicts.add(f)
            continue
        h.values[f], h.quotes[f] = v, quote
    for f in conflicts:
        h.values.pop(f, None)
        h.quotes.pop(f, None)
    return h


def extract_llm(text: str, client, groups: list[str] | None = None, m: Manifest | None = None) -> LLMResult:
    m = m or load()
    h = LLMResult(group=list(groups if groups is not None else groups_in_text(text, m)))
    for k in h.group:
        acc = None
        for piece in pieces(text, m.groups[k].terms):
            r = LLMResult()
            data, record = client(system_prompt(k, m), "Teks peraturan:\n" + piece, PROMPT_VERSION)
            r.tokens = int(record.get("token_masuk", 0)) + int(record.get("token_keluar", 0))
            if data is None:
                r.valid = False
                r.error = f"{k}: {record.get('galat') or 'jawaban tidak bisa di-parse'}"
            else:
                parse(data, text, group_field_pattern(k, m), r)
            acc = combine_llm(acc, r)
        if acc is None:
            continue
        h.values.update(acc.values)
        h.quotes.update(acc.quotes)
        h.dropped += acc.dropped
        h.tokens += acc.tokens
        h.valid = h.valid and acc.valid
        if acc.error:
            h.error = (h.error + "; " if h.error else "") + acc.error
    return h


def _leaf_group(path: str) -> str:
    return path.split(".")[0].split("[")[0]


def reread_changed(original: LLMResult, text: str, client, groups: list[str], changed: set[str],
                   m: Manifest | None = None) -> LLMResult:
    text_n = _norm(text)
    stale = {_leaf_group(j) for j, q in original.quotes.items() if q and _norm(q) not in text_n}
    ask = [g for g in groups if g in changed or g in stale]
    fresh = extract_llm(text, client, ask, m)
    kept = {j: v for j, v in original.values.items() if _leaf_group(j) not in ask}
    out = LLMResult(values=kept, quotes={j: q for j, q in original.quotes.items() if j in kept},
                    dropped=[x for x in original.dropped if _leaf_group(x.split(":")[0]) not in ask] + fresh.dropped,
                    valid=original.valid and fresh.valid,
                    error="; ".join(x for x in (original.error if not ask else "", fresh.error) if x),
                    tokens=fresh.tokens, group=list(groups))
    out.values.update(fresh.values)
    out.quotes.update(fresh.quotes)
    return out


def leaves(value, path: str, out: dict | None = None) -> dict[str, Decimal | None]:
    out = {} if out is None else out
    if isinstance(value, dict):
        for k, x in value.items():
            leaves(x, f"{path}.{k}", out)
    elif isinstance(value, list):
        for i, x in enumerate(value):
            leaves(x, f"{path}[{i}]", out)
    else:
        out[path] = None if value is None else Decimal(str(value))
    return out


def finding_leaves(result) -> dict[str, Decimal | None]:
    out: dict[str, Decimal | None] = {}
    for h in result:
        for t in h.findings:
            leaves(t.value, t.key, out)
    return out
