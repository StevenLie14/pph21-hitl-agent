from __future__ import annotations

import functools
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..taxes import get as tax_module
from .identity import RegulationId, canon_id, find_all

DATA_DIR = tax_module().data_dir

WATCHLIST_FILE = DATA_DIR / "watchlist.yaml"
CATEGORIES = ("dasar", "fasilitas", "prosedural", "perlu_ditinjau", "tidak_relevan")
_GENERAL_RULE_TYPES = {"UU", "PERPPU", "PP", "PMK"}
_DJP_ISSUERS = "PJ"


def _fold(text: str) -> str:
    t = re.sub(r"[^A-Z0-9]", "", text.upper())
    return t.translate(str.maketrans({"L": "I", "1": "I", "0": "O"}))


@dataclass(frozen=True)
class WatchlistEntry:
    identity: RegulationId
    role: str
    governs: tuple[str, ...] = ()
    triggers: tuple[RegulationId, ...] = ()
    valid_until: str | None = None
    governed_articles: tuple[tuple[str, tuple[str, ...]], ...] = ()


@dataclass(frozen=True)
class Watchlist:
    regulations: tuple[WatchlistEntry, ...]
    keywords: dict
    keys_from_keywords: dict

    def find(self, ident: RegulationId) -> WatchlistEntry | None:
        for e in self.regulations:
            if e.identity == ident:
                return e
        return None


def _require_id(text: str) -> RegulationId:
    ident = canon_id(text)
    if ident is None:
        raise ValueError(f"identitas watchlist tidak dikenali: {text!r}")
    return ident


@functools.lru_cache(maxsize=4)
def load_watchlist(path: Path | None = None) -> Watchlist:
    data = yaml.safe_load(Path(path or WATCHLIST_FILE).read_text(encoding="utf-8"))
    entries = tuple(
        WatchlistEntry(
            identity=_require_id(p["id"]),
            role=p["peran"],
            governs=tuple(p.get("mengatur", [])),
            triggers=tuple(_require_id(x) for x in p.get("pemicu", [])),
            valid_until=str(p["berlaku_sampai"]) if p.get("berlaku_sampai") else None,
            governed_articles=tuple((str(k), tuple(v)) for k, v in (p.get("mengatur_pasal") or {}).items()),
        )
        for p in data["peraturan"]
    )
    return Watchlist(entries, data["kata_kunci"], data.get("key_dari_kata_kunci", {}))


@dataclass
class Classification:
    category: str
    reasons: list[str] = field(default_factory=list)
    affected_keys: list[str] = field(default_factory=list)
    related_ids: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return self.category != "tidak_relevan"


def _contains(words: list[str], folded: str) -> list[str]:
    return [k for k in words if _fold(k) in folded]


def _add_unique(items: list[str], values) -> None:
    for v in values:
        if v not in items:
            items.append(v)


def classify(
    title: str,
    subject: str = "",
    doc_id: RegulationId | None = None,
    watchlist: Watchlist | None = None,
) -> Classification:
    wl = watchlist or load_watchlist()
    text = f"{title} {subject}"
    folded = _fold(text)
    kw = wl.keywords
    ident = doc_id or canon_id(title)

    strong = _contains(kw["kuat"], folded)
    facility = _contains(kw["fasilitas"], folded)
    procedural = _contains(kw["prosedural"], folded)
    other = _contains(kw["objek_lain"], folded)
    other_pph = _contains(kw.get("objek_pph_lain", []), folded)
    employee = _contains(kw["konteks_pegawai"], folded)
    articles = set(re.findall(r"PASAL\s+(\d+)", re.sub(r"\s+", " ", text.upper())))
    if articles and "21" not in articles and articles - {"26"}:
        other_pph.append("PPh Pasal " + "/".join(sorted(articles, key=int)))
        strong = [k for k in strong if k != "PASAL 26"]
    pph = _fold("PAJAK PENGHASILAN") in folded
    pajak = _fold("PAJAK") in folded
    from_djp = bool(ident and ident.kind in ("PER", "SE", "KEP") and ident.issuer == _DJP_ISSUERS)
    general_rule = bool(ident and ident.kind in _GENERAL_RULE_TYPES)

    result = Classification("tidak_relevan")

    mentioned = [i for i in find_all(text) if i != ident]
    related = [(i, wl.find(i)) for i in mentioned]
    related = [(i, e) for i, e in related if e is not None]
    if related:
        result.related_ids = [str(i) for i, _ in related]
        roles = {e.role for _, e in related}
        for _, e in related:
            _add_unique(result.affected_keys, e.governs)
            _add_unique(result.triggers, [str(p) for p in e.triggers])
        result.category = "dasar" if "dasar" in roles else ("fasilitas" if "fasilitas" in roles else "prosedural")
        result.reasons.append(f"menyebut peraturan watchlist: {', '.join(result.related_ids)}")
        if result.category == "fasilitas":
            result.affected_keys = []
        return result

    if strong:
        result.reasons.append(f"kata kunci PPh 21/26: {', '.join(strong)}")
        if facility:
            result.category = "fasilitas"
            result.reasons.append(f"fasilitas: {', '.join(facility)}")
            return result
        if from_djp and procedural:
            result.category = "prosedural"
            result.reasons.append(f"peraturan Dirjen Pajak bersifat prosedural: {', '.join(procedural)}")
            return result
        for words, keys in wl.keys_from_keywords.items():
            if _fold(words) in folded:
                _add_unique(result.affected_keys, keys)
        if general_rule:
            result.category = "dasar"
            result.reasons.append(f"jenis {ident.kind} dapat mengubah angka")
            if not result.affected_keys:
                result.reasons.append("key data terdampak tidak teridentifikasi dari judul, tinjau manual")
        else:
            result.category = "perlu_ditinjau"
        for e in wl.regulations:
            if set(e.governs) & set(result.affected_keys):
                _add_unique(result.triggers, [str(p) for p in e.triggers])
        return result

    if other_pph:
        result.reasons.append(f"objek PPh selain Pasal 21: {', '.join(other_pph)}")
        return result

    withholding = _fold("BUKTI PEMOTONGAN") in folded or _fold("SURAT PEMBERITAHUAN MASA") in folded
    if from_djp and procedural and (pph or (withholding and not other)):
        result.category = "prosedural"
        result.reasons.append(f"peraturan Dirjen Pajak tentang PPh/pemotongan, prosedural: {', '.join(procedural)}")
        return result

    if other:
        result.reasons.append(f"objek pajak lain: {', '.join(other)}")
        return result
    if ident and ident.kind in ("UU", "PERPPU", "PP") and (pph or _fold("PERPAJAKAN") in folded):
        result.category = "perlu_ditinjau"
        result.reasons.append(
            f"{ident.kind} tentang perpajakan/PPh secara umum: bisa mengubah UU PPh atau aturan PPh 21 "
            "tanpa menyebutnya di judul"
        )
        return result
    if facility and pajak and general_rule:
        result.category = "perlu_ditinjau"
        result.reasons.append(
            f"fasilitas pajak tanpa menyebut objeknya ({', '.join(facility)}); bisa mencakup PPh 21 DTP"
        )
        return result
    if pph and employee:
        result.category = "perlu_ditinjau"
        result.reasons.append(f"PPh dalam konteks penghasilan orang pribadi: {', '.join(employee)}")
        return result
    return result
