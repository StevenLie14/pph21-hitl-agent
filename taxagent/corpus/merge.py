from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..monitor.identity import RegulationId, canon_id

_TYPE_NAMES = {
    "Peraturan Menteri Keuangan": "PERATURAN MENTERI KEUANGAN",
    "Keputusan Menteri Keuangan": "KEPUTUSAN MENTERI KEUANGAN",
    "Peraturan Pemerintah": "PERATURAN PEMERINTAH",
    "Peraturan Presiden": "PERATURAN PRESIDEN",
    "Undang-Undang": "UNDANG-UNDANG",
    "Perpu": "PERPPU",
    "Peraturan Pemerintah Pengganti Undang-Undang": "PERPPU",
    "Peraturan Menteri": "PERATURAN MENTERI KEUANGAN",
    "Keputusan Menteri": "KEPUTUSAN MENTERI KEUANGAN",
}
_DIRJEN_PREFIX = {
    "Peraturan Dirjen Pajak": "PER", "Keputusan Dirjen Pajak": "KEP", "Peraturan Dirjen Bea dan Cukai": "PER",
    "Peraturan Dirjen Perbendaharaan": "PER", "Peraturan Bersama Dirjen": "PER",
    "Keputusan Ketua Pengadian Pajak": "KEP", "Peraturan Unit Eselon I": "PER", "Keputusan Unit Eselon I": "KEP",
}
_RE_N_YEAR = re.compile(r"^\D{0,12}?(\d{1,4})\s+TAHUN\s+(\d{4})$")
_RE_KMK_MK_DOT = re.compile(r"^(?:KMK\s*-?\s*)?(\d{1,4})\s*/\s*MK\.(\d{1,2})\s*/\s*(\d{4})$")
_RE_DIRJEN_NO_PREFIX = re.compile(
    r"^(?:[A-Za-z]+\s+)?(?:PER|KEP|P)?-?\s*(\d{1,4})\s*/\s*([A-Z]{1,5}(?:\.[A-Z0-9]{1,4})?)\s*/\s*(\d{4})$")
_RE_KEPPRES = re.compile(r"^(?:K(?:EP)?PRES\s+)?(?:NOMOR\s+)?(\d{1,4})\s+TAHUN\s+(\d{4})$")


def normalize_number(number: str) -> str:
    number = (number or "").replace("\xa0", " ").replace("Â", " ").upper()
    number = re.sub(r"(\d)\s*TAHUN\s*(\d)", r"\1 TAHUN \2", number)
    number = re.sub(r"\.\s*/", "/", number)
    return " ".join(number.split()).strip(" .,")


def listing_id(kind: str, number: str) -> RegulationId | None:
    number = normalize_number(number)
    if not number:
        return None
    if kind == "Keputusan Presiden" or re.match(r"K(?:EP)?PRES\b", number):
        m = _RE_KEPPRES.match(number)
        return RegulationId("KEPPRES", int(m.group(1)), int(m.group(2))) if m else None
    if kind in ("Keputusan Menteri Keuangan", "Keputusan Menteri") and (m := _RE_KMK_MK_DOT.match(number)):
        return RegulationId("KMK", int(m.group(1)), int(m.group(3)), f"MK{m.group(2)}")
    if kind in ("Peraturan Dirjen Pajak", "Keputusan Dirjen Pajak") and (m := _RE_N_YEAR.match(number)):
        return RegulationId(_DIRJEN_PREFIX[kind], int(m.group(1)), int(m.group(2)), "PJ")
    if kind in _DIRJEN_PREFIX:
        m = _RE_DIRJEN_NO_PREFIX.match(number)
        if m:
            return RegulationId(_DIRJEN_PREFIX[kind], int(m.group(1)), int(m.group(3)),
                                m.group(2).replace(".", ""))
    if kind in _TYPE_NAMES:
        m = _RE_N_YEAR.match(number)
        if m:
            return canon_id(f"{_TYPE_NAMES[kind]} NOMOR {m.group(1)} TAHUN {m.group(2)}")
        return canon_id(number)
    if kind in _DIRJEN_PREFIX:
        return canon_id(number)
    return None


@dataclass
class SourceDoc:
    source: str
    id: str
    kind: str
    number: str
    title: str
    year: int | None
    has_text: bool
    quality: str | None = None


@dataclass
class IndexEntry:
    sumber: str
    id: str
    kunci: str | None
    jenis: str
    nomor: str
    judul: str
    tahun: int | None
    mutu: str | None
    pasangan: str | None = None
    kemiripan_judul: float | None = None
    catatan: list[str] = field(default_factory=list)
    judul_teks: str | None = None


def similarity(a: str, b: str) -> float | None:
    wa = [k for k in re.findall(r"[a-z0-9]+", a.lower()) if len(k) >= 3]
    wb = [k for k in re.findall(r"[a-z0-9]+", b.lower()) if len(k) >= 3]
    if not wa or not wb:
        return None
    shorter, longer = sorted((wa, wb), key=len)
    joined = "".join(longer)
    return round(sum(1 for k in shorter if k in joined) / len(shorter), 3)


def _entry(m: SourceDoc, k: RegulationId | None) -> IndexEntry:
    return IndexEntry(m.source, m.id, str(k) if k else None, m.kind, m.number, m.title, m.year, m.quality)


def merge_sources(jdih: list[SourceDoc], pajak: list[SourceDoc]) -> tuple[list[IndexEntry], dict]:
    counts: dict[str, int] = dict.fromkeys(
        ("jdih", "jdih_tanpa_kunci", "jdih_tanpa_teks", "pajak", "pajak_tanpa_kunci", "pajak_teks_kosong", "cocok",
         "pajak_mengganti_jdih", "pajak_duplikat", "hanya_pajak"), 0)
    by_key: dict[RegulationId, list[IndexEntry]] = {}
    index: list[IndexEntry] = []
    for m in jdih:
        k = listing_id(m.kind, m.number)
        e = _entry(m, k)
        counts["jdih"] += 1
        counts["jdih_tanpa_kunci"] += k is None
        if not m.has_text:
            counts["jdih_tanpa_teks"] += 1
            e.catatan.append("tanpa teks")
        if k is not None:
            by_key.setdefault(k, []).append(e)
        index.append(e)

    usable = {k for k, es in by_key.items()
              if any("tanpa teks" not in e.catatan and e.mutu != "tidak_terpakai" for e in es)}
    seen: set[RegulationId] = set()
    for m in pajak:
        counts["pajak"] += 1
        k = listing_id(m.kind, m.number)
        e = _entry(m, k)
        has_text = m.has_text and m.quality != "tidak_terpakai"
        if k is None:
            counts["pajak_tanpa_kunci"] += 1
        elif k in seen:
            counts["pajak_duplikat"] += 1
            continue
        if k is not None:
            seen.add(k)
        if m.has_text and not has_text:
            counts["pajak_teks_kosong"] += 1
            e.catatan.append("tanpa teks")
        counterpart = by_key.get(k, []) if k is not None else []
        if counterpart:
            counts["cocok"] += 1
            j = counterpart[0]
            score = similarity(m.title, j.judul)
            j.pasangan, j.kemiripan_judul = m.id, score
            e.pasangan, e.kemiripan_judul = j.id, score
            if k in usable:
                continue
            if not has_text:
                continue
            counts["pajak_mengganti_jdih"] += 1
            e.catatan.append("JDIH tanpa teks terpakai")
        else:
            counts["hanya_pajak"] += 1
        if m.has_text:
            index.append(e)
    return index, counts


DOUBT_SIMILARITY = 0.5
SAME_TEXT_SIMILARITY = 0.8
_RE_ABOUT = re.compile(
    r"\bTENTANG\s+(.{10,400}?)\s+(?:DENGAN\s+RAHMAT|MENTERI\s+KEUANGAN|PRESIDEN\s+REPUBLIK|DIREKTUR\s+JENDERAL"
    r"|MENIMBANG\b|BAHWA\b)", re.I | re.S)


def title_from_text(text: str) -> str | None:
    m = _RE_ABOUT.search(" ".join(text[:4000].split()))
    return m.group(1).strip(" .,:;") if m else None


def check_doubtful(j: IndexEntry, p: IndexEntry, text_j: str, text_p: str | None) -> str:
    tj = title_from_text(text_j)
    match_j = tj is not None and (similarity(tj, j.judul) or 0) >= DOUBT_SIMILARITY
    match_p = tj is not None and (similarity(tj, p.judul) or 0) >= DOUBT_SIMILARITY
    same = bool(text_p) and (similarity(text_j[:3000], text_p[:3000]) or 0) >= SAME_TEXT_SIMILARITY
    if same:
        result = "sama"
        if tj and not match_j:
            j.judul_teks = tj
            j.catatan.append("judul listing JDIH tidak sesuai teks")
        if tj and not match_p:
            p.catatan.append("judul listing pajak.go.id tidak sesuai teks")
    elif match_j and not match_p:
        result = "lepas"
        j.pasangan = p.pasangan = None
        j.catatan.append(f"pasangan pajak.go.id {p.id} dilepas: judul dan teks berbeda")
        p.catatan.append("kunci sama dengan dokumen JDIH lain, pasangan dilepas")
    elif match_p and not match_j:
        result = "judul_jdih_salah"
        j.judul_teks = tj
        j.catatan.append("judul listing JDIH tidak sesuai teks")
    else:
        result = "tidak_pasti"
        j.catatan.append("pasangan ragu: judul listing berbeda, teks tidak bisa memutuskan")
    return result
