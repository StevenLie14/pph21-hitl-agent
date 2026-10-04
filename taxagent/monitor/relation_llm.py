from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field

PROMPT_VERSION = "relasi-v1-2026-10-08"
RELATION_TYPES = ("mencabut", "mencabut_sebagian", "mengubah")
REGULATION_TYPES = {
    "UU": ("undang-undang", "undang undang", "uu"),
    "PERPPU": ("pengganti undang", "perppu", "perpu"),
    "PP": ("peraturan pemerintah", "pp"),
    "PERPRES": ("peraturan presiden", "perpres"),
    "PMK": ("peraturan menteri keuangan", "pmk"),
    "KMK": ("keputusan menteri keuangan", "kmk"),
    "PER": ("peraturan direktur jenderal", "per"),
    "KEP": ("keputusan direktur jenderal", "kep"),
    "SE": ("surat edaran", "se"),
}
KEYWORDS = ("beberapa ketentuan dalam", "ketentuan penutup", "dicabut", "tidak berlaku", "mengubah",
              "diubah sebagai berikut", "perubahan atas", "perubahan keputusan")
INSTRUCTION_WORDS = ("sehingga", "disisipkan", "dihapus.")

DOCUMENT_PROMPT = """\
Anda membaca cuplikan sebuah peraturan perundang-undangan Indonesia dan mencatat relasinya dengan \
peraturan LAIN. Catat hanya relasi yang DITETAPKAN oleh dokumen ini:
- mencabut: dokumen ini mencabut seluruh peraturan lain ("... dicabut dan dinyatakan tidak berlaku");
- mencabut_sebagian: dokumen ini mencabut sebagian pasal/ayat/lampiran peraturan lain;
- mengubah: dokumen ini mengubah peraturan lain ("Beberapa ketentuan dalam X diubah", "Mengubah \
beberapa ketentuan dalam X").

JANGAN catat: rujukan di konsiderans atau "Mengingat"; frasa "X sebagaimana telah diubah dengan Y" \
(itu riwayat X, bukan perubahan oleh dokumen ini); peraturan yang dinyatakan tetap berlaku; teks status \
atau riwayat halaman web di ujung dokumen (mis. "Status Peraturan Dicabut", "Daftar Historis Peraturan").
Bila dokumen mencabut "X sebagaimana telah diubah dengan Y", catat X saja.

Untuk setiap relasi beri: jenis, jenis_peraturan (UU, PERPPU, PP, PERPRES, PMK, KMK, PER, KEP, SE), \
nomor (angka saja), tahun, dan kutipan: potongan VERBATIM dari cuplikan yang memuat nama peraturan \
target lengkap dengan nomor dan tahunnya (10-60 kata), disalin persis tanpa "...".

Jawab HANYA JSON: {"relasi": [{"jenis": "...", "jenis_peraturan": "...", "nomor": "...", "tahun": "...", \
"kutipan": "..."}]}"""

ARTICLE_PROMPT = """\
Anda membaca daftar instruksi perubahan dari sebuah peraturan yang mengubah {target}. Sebutkan setiap \
pasal {target} yang DIUBAH, DISISIPKAN, atau DIHAPUS oleh instruksi itu. Pasal yang hanya disebut \
sebagai letak sisipan ("di antara Pasal X dan Pasal Y disisipkan Pasal Z": hanya Z) dan bab tanpa \
nomor pasal tidak dihitung. Untuk setiap pasal beri kutipan VERBATIM instruksinya (5-40 kata) yang \
memuat nomor pasal itu.

Jawab HANYA JSON: {{"pasal": [{{"nomor": "7", "kutipan": "..."}}]}}"""


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def excerpt(text: str, limit: int = 20000, before: int = 1500, after: int = 600) -> str:
    t = " ".join((text or "").split())
    if len(t) <= limit:
        return t
    r = t.lower()
    chosen: list[tuple[int, int]] = []
    total = 0
    for k in KEYWORDS:
        for p in sorted(_find_all(r, k), reverse=True):
            a, b = max(0, p - (2 * before if k == "dicabut" else before)), min(len(t), p + after)
            if any(a < y and x < b for x, y in chosen):
                overlap = [(x, y) for x, y in chosen if a < y and x < b]
                merged = (min([a] + [x for x, _ in overlap]), max([b] + [y for _, y in overlap]))
                added = (merged[1] - merged[0]) - sum(y - x for x, y in overlap)
                if total + added > limit:
                    continue
                chosen = [x for x in chosen if x not in overlap] + [merged]
                total += added
            elif total + (b - a) <= limit:
                chosen.append((a, b))
                total += b - a
    return " [...] ".join(t[a:b] for a, b in sorted(chosen))


def _find_all(r: str, k: str):
    i = r.find(k)
    while i >= 0:
        yield i
        i = r.find(k, i + 1)


@dataclass
class Evidence:
    mulai: int
    akhir: int
    klausa: str
    bagian: str
    pasal: str | None = None
    halaman: int | None = None


@dataclass
class Relation:
    jenis: str
    jenis_peraturan: str
    nomor: int
    tahun: int
    kutipan: str
    pasal: list[str] = field(default_factory=list)
    bukti: Evidence | None = None
    penerbit: str | None = None
    ambigu: bool = False
    rantai: bool = False

    @property
    def kunci(self) -> tuple[str, str, int, int]:
        return self.jenis, self.jenis_peraturan, self.nomor, self.tahun

    @property
    def target(self) -> str:
        return f"{self.jenis_peraturan} {self.nomor}/{self.tahun}"


@dataclass
class RelationResult:
    relasi: list[Relation] = field(default_factory=list)
    dibuang: list[str] = field(default_factory=list)
    mentah: list[dict] = field(default_factory=list)
    valid: bool = True
    galat: str = ""
    token: int = 0


def int_number(x) -> int | None:
    s = str(x).strip().split("/")[0].rsplit("-", 1)[-1].strip()
    try:
        return int(s.lstrip("0") or "0")
    except ValueError:
        return None


_FOLD_LETTERS = str.maketrans({"1": "i", "l": "i", "!": "i", "|": "i", "0": "o"})
_FOLD_DIGITS = str.maketrans({"o": "0", "l": "1", "i": "1", "!": "1", "|": "1"})


def fold(text: str) -> str:
    t = (text or "").lower().replace("rn", "m").translate(_FOLD_LETTERS)
    return "".join(ch for ch in t if ch.isalnum())


def fold_digits(text: str) -> str:
    t = (text or "").lower().translate(_FOLD_DIGITS)
    return "".join(ch for ch in t if ch.isalnum())


_RE_MARKER = re.compile(r"(?m)^[ \t]*(?:[A-Za-z]|\d{1,2})[.)][ \t]*\n")


def strip_list_markers(text: str) -> str:
    return _RE_MARKER.sub("", text or "")


def fold_map(text: str) -> tuple[str, list[int]]:
    t = (text or "").lower()
    out: list[str] = []
    idx: list[int] = []
    i = 0
    while i < len(t):
        if t.startswith("rn", i):
            out.append("m")
            idx.append(i)
            i += 2
            continue
        ch = t[i].translate(_FOLD_LETTERS)
        if ch.isalnum():
            out.append(ch)
            idx.append(i)
        i += 1
    return "".join(out), idx


def _strip_markers_map(text: str) -> tuple[str, list[int]]:
    parts, index_map, a = [], [], 0
    for m in _RE_MARKER.finditer(text or ""):
        parts.append(text[a:m.start()])
        index_map.extend(range(a, m.start()))
        a = m.end()
    parts.append((text or "")[a:])
    index_map.extend(range(a, len(text or "")))
    return "".join(parts), index_map


_RE_CONSIDERING = re.compile(r"\bmenimbang\b", re.I)
_RE_RECALLING = re.compile(r"\bmengingat\s*:", re.I)
_RE_DECIDING = re.compile(r"\bM\s?E\s?M\s?U\s?T\s?U\s?S\s?K\s?A\s?N\b|\bmenetapkan\s*:", re.I)
_RE_ELUCIDATION = re.compile(r"(?m)^\s*PENJELASAN\b")
_RE_ATTACHMENT = re.compile(r"(?m)^\s*LAMPIRAN\b")
_RE_ENACTED = re.compile(r"ditetapkan\s+di\b", re.I)
_RE_ARTICLE = re.compile(r"(?m)^\s*(Pasal\s+\d+[A-Za-z]?)\s*$")
_RE_DICTUM = re.compile(r"(?m)^\s*(KESATU|KEDUA|KETIGA|KEEMPAT|KELIMA|KEENAM|KETUJUH|KEDELAPAN|KESEMBILAN|KESEPULUH)\b")


def location(text: str, pos: int) -> tuple[str, str | None]:
    def first(rx: re.Pattern, start: int = 0) -> int | None:
        m = rx.search(text, start)
        return m.start() if m else None

    considering, recalling, deciding = first(_RE_CONSIDERING), first(_RE_RECALLING), first(_RE_DECIDING)
    enacted = first(_RE_ENACTED, deciding or 0)
    markers = [(x, n) for x, n in ((considering, "menimbang"), (recalling, "mengingat"), (deciding, "batang_tubuh"),
                                   (first(_RE_ELUCIDATION, enacted) if enacted else None, "penjelasan"),
                                   (first(_RE_ATTACHMENT, enacted) if enacted else None, "lampiran")) if x is not None]
    if not markers or deciding is None:
        section = "tidak_diketahui"
    else:
        before = [n for x, n in sorted(markers) if x <= pos]
        section = before[-1] if before else "judul"
    article = None
    if section == "batang_tubuh":
        article = next((m.group(1) for m in reversed(list(_RE_ARTICLE.finditer(text, deciding, pos)))), None) or \
            next((m.group(1) for m in reversed(list(_RE_DICTUM.finditer(text, deciding, pos)))), None)
        article = " ".join(article.split()) if article else None
    return section, article


_RE_CLAUSE_START = re.compile(r"[.;:]\s|\n\s*(?:[a-z]|\d{1,2})[.)]\s|\n\s*\(\d{1,2}\)|^[ \t]*Pasal\s+\d+[A-Za-z]?[ \t]*\n",
                             re.M)
_RE_SENTENCE_END = re.compile(r"\.(?=\s+(?:[A-Z(]|\d{1,2}[.)]\s)|\s*$)")


def clause(text: str, a: int, b: int, limit: int = 2500) -> tuple[int, int]:
    floor = max(0, a - 600)
    bounds = [m.end() for m in _RE_CLAUSE_START.finditer(text, floor, a)]
    start = bounds[-1] if bounds else floor
    m = _RE_SENTENCE_END.search(text, b)
    end = m.end() if m else len(text)
    return start, min(end, start + limit)


_RE_CHAIN = re.compile(r"sebagaimana\s+(?:telah\s+)?(?:beberapa\s+kali\s+)?(?:terakhir\s+)?diubah", re.I)


def _target_id(clause_text: str, jp: str, number: int, year: int) -> tuple[str | None, bool]:
    from .identity import find_all_positions

    t = " ".join(clause_text.upper().split())
    issuer, chained = None, False
    for ident, a, _ in find_all_positions(t):
        if (ident.kind, ident.number, ident.year) != (jp, number, year):
            continue
        issuer = issuer or ident.issuer
        if _RE_CHAIN.search(t[max(0, a - 160):a]):
            chained = True
    return issuer, chained


class _Text:
    def __init__(self, text: str, page_starts: list[int] | None = None):
        self.text, self.page_starts = text or "", page_starts
        self.folded, self.index_map = fold_map(self.text)
        self._markers: tuple[str, list[int]] | None = None

    def markers(self) -> tuple[str, list[int]]:
        if self._markers is None:
            t, map_t = _strip_markers_map(self.text)
            folded, map_l = fold_map(t)
            self._markers = (folded, [map_t[i] for i in map_l])
        return self._markers

    def page(self, pos: int) -> int | None:
        return bisect.bisect_right(self.page_starts, pos) if self.page_starts else None

    def evidence(self, a: int, b: int) -> Evidence:
        start, end = clause(self.text, a, b)
        section, article = location(self.text, a)
        return Evidence(start, end, self.text[start:end].strip(), section, article, self.page(a))


def _type_near_number(quote: str, jp: str, number: int) -> bool:
    if jp not in ("UU", "PERPPU", "PP", "PERPRES", "PMK"):
        return True
    t = " ".join((quote or "").upper().split())
    t = re.sub(r"(?<=\d)O|O(?=\d)", "0", t)
    others = "|".join(re.escape(n.upper()) for k, ns in REGULATION_TYPES.items() if k != jp for n in ns if len(n) > 4)
    number = r"\s?".join(str(number))
    for n in REGULATION_TYPES[jp]:
        name = r"\s*".join(re.escape(x) for x in n.upper().split())
        pattern = rf"\b{name}\b(?!\s+INI\b)(?:(?!{others}|;).){{0,80}}?\bNOMOR\s*:?\s*(?:[A-Z]+\s*-\s*)?0*{number}(?!\d)"
        if re.search(pattern, t):
            return True
    return bool(re.search(rf"\b{re.escape(jp)}\s*-?\s*0*{number}(?!\d)", t))


def verify(b: dict, text: str | _Text, self_id: tuple[str, int, int] | None) -> tuple[Relation | None, str]:
    tx = text if isinstance(text, _Text) else _Text(text)
    kind, jp = str(b.get("jenis", "")).strip().lower(), str(b.get("jenis_peraturan", "")).strip().upper()
    number, year, quote = int_number(b.get("nomor")), int_number(b.get("tahun")), str(b.get("kutipan", ""))
    if kind not in RELATION_TYPES or jp not in REGULATION_TYPES or not number or not year:
        return None, f"isian tidak lengkap/tidak dikenal: {b}"
    tl, index_map, kl = tx.folded, tx.index_map, fold(quote)
    if len(kl) >= 15 and kl not in tl:
        tl, index_map = tx.markers()
    if len(kl) < 15 or kl not in tl:
        return None, f"{jp} {number}/{year}: kutipan tidak ada di teks"
    ka = fold_digits(quote)
    if str(number) not in ka:
        return None, f"{jp} {number}/{year}: nomor tidak ada di kutipan"
    if str(year) not in ka:
        return None, f"{jp} {number}/{year}: tahun tidak ada di kutipan"
    if not any(fold(n) in kl for n in REGULATION_TYPES[jp]):
        return None, f"{jp} {number}/{year}: jenis peraturan tidak ada di kutipan"
    if not _type_near_number(quote, jp, number):
        return None, f"{jp} {number}/{year}: jenis peraturan tidak menyebut nomor itu di kutipan"
    if self_id and (jp, number, year) == self_id:
        return None, f"{jp} {number}/{year}: menunjuk dokumen itu sendiri"
    in_preamble = False
    for pos in _find_all(tl, kl):
        a, z = index_map[pos], index_map[pos + len(kl) - 1] + 1
        if location(tx.text, a)[0] in ("menimbang", "mengingat"):
            in_preamble = True
            continue
        if kind.startswith("mencabut"):
            nearby = tl[pos:pos + len(kl) + 3200]
            if fold("dicabut") in nearby or fold("tidak berlaku") in nearby:
                break
        else:
            nearby = tl[max(0, pos - 1200):pos + len(kl) + 1200]
            if any(fold(k) in nearby for k in ("diubah", "mengubah", "perubahan")):
                break
    else:
        if in_preamble:
            return None, f"{jp} {number}/{year}: kutipan hanya di Menimbang/Mengingat (rujukan, bukan relasi)"
        verb = "dicabut" if kind.startswith("mencabut") else "diubah"
        return None, f"{jp} {number}/{year}: tidak ada '{verb}' di dekat kutipan"
    evidence = tx.evidence(a, z)
    issuer, chained = _target_id(evidence.klausa, jp, number, year)
    if issuer is None:
        issuer, quote_chained = _target_id(quote, jp, number, year)
        chained = chained or quote_chained
    return Relation(kind, jp, number, year, quote, bukti=evidence, penerbit=issuer,
                  ambigu=jp in ("PER", "KEP", "SE") and issuer is None, rantai=chained), ""


def amendment_instructions(text: str, target: Relation, limit: int = 14000) -> tuple[str, str]:
    t = " ".join((text or "").split())
    r = t.lower()
    start = r.find(_normalize(target.kutipan))
    start = max(0, start)
    end = len(t)
    for i in _find_all(r, "beberapa ketentuan dalam"):
        if i <= start + len(target.kutipan):
            continue
        seg = r[i:i + 250]
        same_target = f"nomor {target.nomor} tahun {target.tahun}" in seg or (
            f"{target.nomor}/" in seg and str(target.tahun) in seg)
        if not same_target:
            end = i
            break
    cuts, total = [], 0
    for k in INSTRUCTION_WORDS:
        for i in _find_all(r[start:end], k):
            cuts.append(start + i)
    pieces, last = [], -1
    for p in sorted(set(cuts)):
        a = max(start, p - 300, last)
        if a >= p + 40:
            continue
        s = t[a:p + 40]
        if total + len(s) > limit:
            break
        if pieces and a == last:
            pieces[-1] += s
        else:
            pieces.append(s)
        total += len(s)
        last = p + 40
    return "\n".join(pieces), t[start:end]


def verify_articles(b: dict, region_text: str) -> tuple[str | None, str]:
    number = "".join(str(b.get("nomor", "")).split()).upper()
    quote = str(b.get("kutipan", ""))
    kl = fold(quote)
    if not number or len(kl) < 10 or kl not in fold(region_text):
        return None, f"pasal {number}: kutipan tidak ada di instruksi"
    if fold(f"pasal {number}") not in kl:
        return None, f"pasal {number}: nomor pasal tidak ada di kutipan"
    return number, ""


def extract_relations(text: str, client, self_id: tuple[str, int, int] | None = None,
                   page_starts: list[int] | None = None) -> RelationResult:
    h = RelationResult()
    tx = _Text(text, page_starts)
    data, record = client(DOCUMENT_PROMPT, "Cuplikan:\n" + excerpt(text), PROMPT_VERSION)
    h.token += int(record.get("token_masuk", 0)) + int(record.get("token_keluar", 0))
    if not isinstance(data, dict) or not isinstance(data.get("relasi"), list):
        h.valid, h.galat = False, record.get("galat") or "jawaban bukan JSON {\"relasi\": [...]}"
        return h
    seen = set()
    for b in data["relasi"]:
        if not isinstance(b, dict):
            continue
        h.mentah.append(b)
        r, reason = verify(b, tx, self_id)
        if r is None:
            h.dibuang.append(reason)
        elif r.kunci not in seen:
            seen.add(r.kunci)
            h.relasi.append(r)
    for r in h.relasi:
        if r.jenis != "mengubah":
            continue
        ins, region = amendment_instructions(text, r)
        if not ins:
            continue
        data, record = client(ARTICLE_PROMPT.format(target=f"{r.jenis_peraturan} Nomor {r.nomor} Tahun {r.tahun}"),
                          "Instruksi perubahan:\n" + ins, PROMPT_VERSION)
        h.token += int(record.get("token_masuk", 0)) + int(record.get("token_keluar", 0))
        if not isinstance(data, dict) or not isinstance(data.get("pasal"), list):
            h.dibuang.append(f"{r.target}: jawaban pasal tidak valid")
            continue
        for b in data["pasal"]:
            if not isinstance(b, dict):
                continue
            p, reason = verify_articles(b, region)
            if p is None:
                h.dibuang.append(f"{r.target}: {reason}")
            elif p not in r.pasal:
                r.pasal.append(p)
    return h
