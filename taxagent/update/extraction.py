from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from .amounts import clean_text, parse_terbilang, yaml_number
from .manifest import load

RP = r"RP(\d+(?:\.\d+)?)"
PCT = r"(\d+(?:\.\d+)?)%"

OUT_OF_SCOPE = load().out_of_scope


@dataclass
class Finding:
    key: str
    value: object
    quote: str
    source: str = ""


@dataclass
class ExtractionResult:
    findings: list[Finding] = field(default_factory=list)
    mismatches: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    verified: set[Decimal] = field(default_factory=set)
    without_words: set[Decimal] = field(default_factory=set)


def _d(s: str) -> Decimal:
    return Decimal(s)


def _quote(t: str, m: re.Match, width: int = 40) -> str:
    return t[max(0, m.start() - width):m.end() + width].strip()


def _ptkp(t: str, h: ExtractionResult) -> None:
    if "PENGHASILAN TIDAK KENA PAJAK" not in t:
        return
    own = re.search(rf"{RP} (?:SETAHUN )?UNTUK DIRI WAJIB PAJAK ORANG PRIBADI", t)
    married = re.search(rf"{RP} (?:SETAHUN )?TAMBAHAN UNTUK WAJIB PAJAK YANG KAWIN", t)
    dependant = re.search(rf"{RP} (?:SETAHUN )?TAMBAHAN UNTUK SETIAP ANGGOTA KELUARGA", t)
    max_dep = re.search(r"PALING BANYAK (\d+) \(([A-Z ]+)\) ORANG", t)
    if not (own and married and dependant and max_dep):
        if own or married or dependant:
            h.notes.append("ptkp: hanya sebagian butir terbaca, tidak dipakai")
        return
    n, words = int(max_dep.group(1)), parse_terbilang(max_dep.group(2))
    if words is not None and words != n:
        h.mismatches.append(f"PTKP paling banyak {n} tetapi terbilang ({max_dep.group(2)}) = {words}")
        return
    (h.verified if words == n else h.without_words).add(Decimal(n))
    h.findings.append(Finding("ptkp", {
        "wajib_pajak_sendiri": yaml_number(_d(own.group(1))),
        "tambahan_kawin": yaml_number(_d(married.group(1))),
        "tambahan_tanggungan": yaml_number(_d(dependant.group(1))),
        "maksimal_tanggungan": n,
    }, _quote(t, own, 60)))


def _cost_allowance(t: str, h: ExtractionResult, key: str, phrase: str) -> None:
    m = re.search(
        rf"BESARNYA {phrase} .{{0,120}}?SEBESAR {PCT} DARI PENGHASILAN BRUTO, PALING BANYAK {RP} SETAHUN "
        rf"ATAU PALING BANYAK {RP} SEBULAN",
        t,
    )
    if m:
        percent, yearly, monthly = m.group(1), m.group(2), m.group(3)
    else:
        m = re.search(
            rf"{phrase},? SEBESAR {PCT} DARI PENGHASILAN BRUTO, SETINGGI-TINGGINYA {RP} SEBULAN ATAU {RP} SETAHUN", t,
        )
        if not m:
            return
        percent, monthly, yearly = m.group(1), m.group(2), m.group(3)
    h.findings.append(Finding(key, {
        "persen": yaml_number(_d(percent)),
        "maksimal_sebulan": yaml_number(_d(monthly)),
        "maksimal_setahun": yaml_number(_d(yearly)),
    }, _quote(t, m, 0)))


def _brackets_range_first(seg: str) -> list[tuple[Decimal | None, Decimal | None, Decimal]]:
    rows = []
    for m in re.finditer(rf"(?:DI ATAS {RP} )?SAMPAI DENGAN {RP} {PCT}|DI ATAS {RP} {PCT}", seg):
        if m.group(5) is not None:
            rows.append((_d(m.group(4)), None, _d(m.group(5))))
        else:
            lower = _d(m.group(1)) if m.group(1) else None
            rows.append((lower, _d(m.group(2)), _d(m.group(3))))
    return rows


def _brackets_rate_first(seg: str) -> list[tuple[Decimal | None, Decimal | None, Decimal]]:
    rows = []
    for m in re.finditer(
        rf"SEBESAR {PCT} ATAS PENGHASILAN BRUTO (?:SAMPAI DENGAN {RP}|DI ATAS {RP}(?: SAMPAI DENGAN {RP})?)", seg,
    ):
        p = _d(m.group(1))
        if m.group(2):
            rows.append((None, _d(m.group(2)), p))
        else:
            rows.append((_d(m.group(3)), _d(m.group(4)) if m.group(4) else None, p))
    return rows


def _assemble(rows, name: str, h: ExtractionResult) -> list[dict] | None:
    if len(rows) < 2:
        return None
    for i, (lower, upper, _) in enumerate(rows):
        previous = rows[i - 1][1] if i else None
        if (i == 0 and lower not in (None, 0)) or (i and lower != previous):
            h.notes.append(f"{name}: lapisan tidak bersambung pada baris {i + 1}, tidak dipakai")
            return None
        if (upper is None) != (i == len(rows) - 1):
            h.notes.append(f"{name}: hanya lapisan terakhir yang boleh tak terbatas, tidak dipakai")
            return None
    return [{"batas_atas": yaml_number(a) if a is not None else None, "persen": yaml_number(p)} for _, a, p in rows]


def _article_17(t: str, h: ExtractionResult) -> None:
    m = re.search(r"WAJIB PAJAK ORANG PRIBADI DALAM NEGERI SEBAGAI BERIKUT:(.*?)(?:\bB\. WAJIB PAJAK BADAN|$)", t)
    if not m or "PENGHASILAN KENA PAJAK" not in t[:m.end()]:
        return
    rows = _assemble(_brackets_range_first(m.group(1)), "tarif_pasal_17", h)
    if rows:
        h.findings.append(Finding("tarif_pasal_17", rows, m.group(0)[:200] + " ..."))


def _final_pp68(t: str, h: ExtractionResult) -> None:
    for key, phrase in (("pph_final_pesangon", r"UANG PESANGON"), ("pph_final_manfaat_pensiun", r"UANG MANFAAT PENSIUN")):
        m = re.search(rf"TARIF PAJAK PENGHASILAN PASAL 21 ATAS PENGHASILAN BERUPA {phrase}[^:]*:(.*?)(?=\bPASAL \d|$)", t)
        if m:
            rows = _assemble(_brackets_rate_first(m.group(1)), key, h)
            if rows:
                h.findings.append(Finding(key, rows, m.group(0)[:200] + " ..."))


def _honorarium_pns(t: str, h: ExtractionResult) -> None:
    grades: dict[str, object] = {}
    first_match = None
    for m in re.finditer(rf"SEBESAR {PCT} DARI JUMLAH BRUTO HONORARIUM ATAU IMBALAN LAIN BAGI ([^;.]*)", t):
        first_match = first_match or m
        for g in re.findall(r"\bPNS GOLONGAN (IV|III|II|I)\b|\bDAN GOLONGAN (IV|III|II|I)\b", m.group(2)):
            grades[g[0] or g[1]] = yaml_number(_d(m.group(1)))
    if set(grades) == {"I", "II", "III", "IV"}:
        h.findings.append(Finding("pph_final_honorarium_pns", {k: grades[k] for k in ("I", "II", "III", "IV")}, _quote(t, first_match, 0)))
    elif grades:
        h.notes.append(f"pph_final_honorarium_pns: hanya golongan {sorted(grades)} terbaca, tidak dipakai")


def _non_employee(t: str, h: ExtractionResult) -> None:
    m = re.search(rf"DASAR PENGENAAN DAN PEMOTONGAN PAJAK PENGHASILAN PASAL 21 UNTUK BUKAN PEGAWAI YAITU SEBESAR {PCT}", t)
    if m:
        h.findings.append(Finding("bukan_pegawai", {"dpp_persen": yaml_number(_d(m.group(1)))}, _quote(t, m, 0)))


def _daily_ter(t: str, h: ExtractionResult) -> None:
    values, quotes = {}, []
    m = re.search(rf"PENGHASILAN BRUTO SEHARI LEBIH DARI {RP},? SEBESAR {PCT} DARI JUMLAH PENGHASILAN BRUTO", t)
    if m:
        values["batas_atas_ter_harian"] = yaml_number(_d(m.group(1)))
        values["dpp_persen_di_atas_batas"] = yaml_number(_d(m.group(2)))
        quotes.append(_quote(t, m, 0))
    m = re.search(rf"SAMPAI DENGAN JUMLAH {RP} SEHARI TIDAK DIKENAKAN PEMOTONGAN", t)
    if m:
        values["batas_bebas_harian"] = yaml_number(_d(m.group(1)))
        quotes.append(_quote(t, m, 60))
    if values:
        h.findings.append(Finding("ter_harian", values, " | ".join(quotes)))


_IN_KIND_PATTERN = {
    "kupon_batas_sebulan":
        rf"NILAI KUPON .{{0,200}}?TIDAK MELEBIHI: A\. {RP} UNTUK TIAP PEGAWAI DALAM JANGKA WAKTU 1 \(SATU\) BULAN",
    "bingkisan_batas_setahun":
        rf"\bBINGKISAN\b(?:(?!PERALATAN|OLAHRAGA|TEMPAT TINGGAL|KENDARAAN).){{0,400}}?{RP} UNTUK TIAP PEGAWAI DALAM "
        rf"JANGKA WAKTU 1 \(SATU\) TAHUN PAJAK",
    "olahraga_batas_setahun":
        rf"FASILITAS OLAHRAGA(?:(?!BINGKISAN|TEMPAT TINGGAL|KENDARAAN).){{0,400}}?{RP} UNTUK TIAP PEGAWAI DALAM "
        rf"JANGKA WAKTU 1 \(SATU\) TAHUN PAJAK",
    "tempat_tinggal_batas_sebulan":
        rf"\(INDIVIDUAL\)(?:(?!KENDARAAN|OLAHRAGA|KOMUNAL).){{0,300}}?{RP} UNTUK TIAP PEGAWAI DALAM JANGKA WAKTU 1 "
        rf"\(SATU\) BULAN",
    "kendaraan_batas_rata_bruto_sebulan":
        rf"FASILITAS KENDARAAN(?:(?!TEMPAT TINGGAL|OLAHRAGA).){{0,400}}?RATA-RATA PENGHASILAN BRUTO DALAM 12 "
        rf"\(DUA BELAS\) BULAN TERAKHIR SAMPAI DENGAN {RP} TIAP BULAN",
}


def _in_kind(t: str, h: ExtractionResult) -> None:
    if "NATURA" not in t:
        return
    values, quotes = {}, []
    for sub_key, pattern in _IN_KIND_PATTERN.items():
        m = re.search(pattern, t)
        if m:
            values[sub_key] = yaml_number(_d(m.group(1)))
            quotes.append(_quote(t, m, 0)[-200:])
    if values:
        h.findings.append(Finding("natura", values, " | ".join(quotes)))


EXTRACTORS = (
    _ptkp,
    lambda t, h: _cost_allowance(t, h, "biaya_jabatan", r"BIAYA ?JABATAN"),
    lambda t, h: _cost_allowance(t, h, "biaya_pensiun", r"BIAYA ?PENSIUN"),
    _article_17,
    _final_pp68,
    _honorarium_pns,
    _non_employee,
    _daily_ter,
    _in_kind,
)


def extract_amounts(text: str, source: str = "") -> ExtractionResult:
    b = clean_text(text)
    h = ExtractionResult(mismatches=list(b.mismatches), verified=set(b.verified),
                       without_words=set(b.without_words))
    for f in EXTRACTORS:
        f(b.text, h)
    for x in h.findings:
        x.source = source
    return h
