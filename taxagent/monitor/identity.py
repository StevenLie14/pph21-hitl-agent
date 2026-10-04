from __future__ import annotations

import re
from dataclasses import dataclass, field

_TYPE_NAMES = [
    ("PERATURAN PEMERINTAH PENGGANTI UNDANG-UNDANG", "PERPPU"),
    ("PERATURAN PEMERINTAH PENGGANTI UNDANG UNDANG", "PERPPU"),
    ("PERATURAN MENTERI KEUANGAN", "PMK"),
    ("KEPUTUSAN MENTERI KEUANGAN", "KMK"),
    ("PERATURAN PEMERINTAH", "PP"),
    ("PERATURAN PRESIDEN", "PERPRES"),
    ("KEPUTUSAN PRESIDEN", "KEPPRES"),
    ("KEPPRES", "KEPPRES"),
    ("UNDANG-UNDANG", "UU"),
    ("UNDANG UNDANG", "UU"),
    ("PERPPU", "PERPPU"),
    ("PERPU", "PERPPU"),
    ("PERPRES", "PERPRES"),
    ("PMK", "PMK"),
    ("KMK", "KMK"),
    ("PP", "PP"),
    ("UU", "UU"),
]

_TYPE_ALIASES = "|".join(re.escape(n) for n, _ in _TYPE_NAMES)
_TYPE_MAP = dict(_TYPE_NAMES)

_NUMBER = r"(?<!\d\.)(\d{1,4})(?:\.(\d{1,2}))?"

_RE_NAMED = re.compile(
    rf"\b({_TYPE_ALIASES})\s+(?:REPUBLIK\s+INDONESIA\s+)?(?:NOMOR|NO\.?)?\s*{_NUMBER}\s+TAHUN\s+(\d{{4}})\b"
)
_RE_DG = re.compile(rf"\b(PER|KEP|SE)\s*-\s*{_NUMBER}\s*/\s*([A-Z]{{1,5}}(?:\.\d{{1,2}})?)\s*/\s*(\d{{4}})\b")
_RE_OLD_PMK = re.compile(rf"\b{_NUMBER}\s*/\s*PMK\.?\s*(\d{{1,3}})\s*/\s*(\d{{4}})\b")
_RE_OLD_KMK = re.compile(rf"\b{_NUMBER}\s*/\s*KMK\.?\s*(\d{{1,3}})\s*/\s*(\d{{4}})\b")
_RE_KMK_UNIT = re.compile(
    r"\b(?<!\d\.)(\d{1,4})\s*/\s*(MK|KM(?:\.\d{1,2})?)\s*/\s*(?:([A-Z]{1,5}(?:\.\d{1,2})?)\s*/\s*)?(\d{4})\b"
)
_RE_KMK_STR = re.compile(r"\bKMK\s+(\d{1,4})(?:\.(\d{1,2}))?\s*/\s*([A-Z]{1,5}\d{0,2})\s*/\s*(\d{4})\b")

_SLUG_OLD_PMK = re.compile(r"^(\d{1,4})(?:-(\d{1,2}))?-pmk-(\d{1,3})-(\d{4})$")
_SLUG_OLD_KMK = re.compile(r"^(\d{1,4})(?:-(\d{1,2}))?-kmk-(\d{1,3})-(\d{4})$")
_SLUG_DG = re.compile(r"^(per|kep|se)-(\d{1,4})([a-z]{1,5}\d{0,2})(\d{4})$")
_SLUG_KMK_UNIT = re.compile(r"^(?:kmk-)?(\d{1,4})(mk|km)([a-z0-9]{0,6}?)(\d{4})$")


def _unit(text: str | None) -> str | None:
    if not text:
        return None
    return text.replace(".", "").upper() or None


def _sub(text: str | None) -> int | None:
    return int(text) if text else None


@dataclass(frozen=True)
class RegulationId:
    kind: str
    number: int
    year: int
    issuer: str | None = None
    old_unit: str | None = field(default=None, compare=False, hash=False)
    sub: int | None = None

    def _number_text(self) -> str:
        return f"{self.number}.{self.sub}" if self.sub is not None else str(self.number)

    def __str__(self) -> str:
        if self.kind in ("PER", "KEP", "SE"):
            return f"{self.kind}-{self._number_text()}/{self.issuer}/{self.year}"
        if self.issuer:
            return f"{self.kind} {self._number_text()}/{self.issuer}/{self.year}"
        return f"{self.kind} {self._number_text()} Tahun {self.year}"


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.upper())


def find_all_positions(text: str) -> list[tuple[RegulationId, int, int]]:
    t = text if text == _normalize(text) else _normalize(text)
    found: list[tuple[RegulationId, int, int]] = []

    def add(m: re.Match, ident: RegulationId) -> None:
        a, b = m.span()
        if any(a < y and x < b for _, x, y in found):
            return
        found.append((ident, a, b))

    for m in _RE_DG.finditer(t):
        add(m, RegulationId(m.group(1), int(m.group(2)), int(m.group(5)), _unit(m.group(4)), sub=_sub(m.group(3))))
    for m in _RE_OLD_PMK.finditer(t):
        add(m, RegulationId("PMK", int(m.group(1)), int(m.group(4)), old_unit=f"PMK.{m.group(3)}",
                            sub=_sub(m.group(2))))
    for m in _RE_OLD_KMK.finditer(t):
        add(m, RegulationId("KMK", int(m.group(1)), int(m.group(4)), _unit(f"KMK{m.group(3)}"), sub=_sub(m.group(2))))
    for m in _RE_KMK_UNIT.finditer(t):
        unit = m.group(3) or m.group(2)
        add(m, RegulationId("KMK", int(m.group(1)), int(m.group(4)), _unit(unit)))
    for m in _RE_KMK_STR.finditer(t):
        add(m, RegulationId("KMK", int(m.group(1)), int(m.group(4)), m.group(3), sub=_sub(m.group(2))))
    for m in _RE_NAMED.finditer(t):
        add(m, RegulationId(_TYPE_MAP[m.group(1)], int(m.group(2)), int(m.group(4)), sub=_sub(m.group(3))))
    return sorted(found, key=lambda x: x[1])


def find_all(text: str) -> list[RegulationId]:
    result: list[RegulationId] = []
    for ident, _, _ in find_all_positions(text):
        if ident not in result:
            result.append(ident)
    return result


def canon_id(text: str) -> RegulationId | None:
    found = find_all(text)
    return found[0] if found else None


_RE_SHORT = re.compile(
    rf"\b({_TYPE_ALIASES})\s*-?\s*(?:NOMOR\s+|NO\.?\s*)?(\d{{1,4}})(?:\s*[/-]\s*|\s+(?:THN|TH)\.?\s*)(\d{{4}})\b")
_RE_DG_SPACED = re.compile(r"\b(PER|KEP|SE)\s+(\d{1,4})\s*/\s*([A-Z]{1,5}(?:\.\d{1,2})?)\s*/\s*(\d{4})\b")
_POPULAR_NAMES = [
    (re.compile(r"\bUU\s+HPP\b|\bHARMONISASI\s+PERATURAN\s+PERPAJAKAN\b"), RegulationId("UU", 7, 2021)),
]


def canon_id_query(text: str) -> RegulationId | None:
    ident = canon_id(text)
    if ident is not None:
        return ident
    t = _normalize(text)
    m = _RE_SHORT.search(t)
    if m and m.group(1) not in ("KMK",):
        return RegulationId(_TYPE_MAP[m.group(1)], int(m.group(2)), int(m.group(3)))
    m = _RE_DG_SPACED.search(t)
    if m:
        return RegulationId(m.group(1), int(m.group(2)), int(m.group(4)), _unit(m.group(3)))
    for pattern, ident in _POPULAR_NAMES:
        if pattern.search(t):
            return ident
    return None


def find_all_query(text: str) -> list[RegulationId]:
    t = _normalize(text)
    spans = [(a, b) for _, a, b in find_all_positions(t)]
    found = [(a, ident) for ident, a, _ in find_all_positions(t)]

    def free(m: re.Match) -> bool:
        a, b = m.span()
        return not any(a < y and x < b for x, y in spans)

    for m in _RE_SHORT.finditer(t):
        if free(m) and m.group(1) != "KMK":
            found.append((m.start(), RegulationId(_TYPE_MAP[m.group(1)], int(m.group(2)), int(m.group(3)))))
    for m in _RE_DG_SPACED.finditer(t):
        if free(m):
            found.append((m.start(), RegulationId(m.group(1), int(m.group(2)), int(m.group(4)), _unit(m.group(3)))))
    result: list[RegulationId] = []
    for _, ident in sorted(found, key=lambda x: x[0]):
        if ident not in result:
            result.append(ident)
    return result


def from_slug(slug: str) -> RegulationId | None:
    s = slug.strip().strip("/").rsplit("/", 1)[-1].lower()
    m = _SLUG_OLD_PMK.match(s)
    if m:
        return RegulationId("PMK", int(m.group(1)), int(m.group(4)), old_unit=f"PMK.{m.group(3)}", sub=_sub(m.group(2)))
    m = _SLUG_OLD_KMK.match(s)
    if m:
        return RegulationId("KMK", int(m.group(1)), int(m.group(4)), _unit(f"KMK{m.group(3)}"), sub=_sub(m.group(2)))
    m = _SLUG_DG.match(s)
    if m:
        return RegulationId(m.group(1).upper(), int(m.group(2)), int(m.group(4)), _unit(m.group(3)))
    m = _SLUG_KMK_UNIT.match(s)
    if m:
        unit = m.group(3) or m.group(2)
        return RegulationId("KMK", int(m.group(1)), int(m.group(4)), _unit(unit))
    return canon_id(s.replace("-", " "))


def document_ids(doc: str, dataset_number: str | None = None) -> RegulationId | None:
    return (canon_id(dataset_number) if dataset_number else None) or canon_id(doc)
