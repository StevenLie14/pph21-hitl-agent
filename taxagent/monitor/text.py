from __future__ import annotations

import datetime as _dt
import difflib
import re
from dataclasses import dataclass, field

from .identity import RegulationId, find_all_positions

MONTHS = ["januari", "februari", "maret", "april", "mei", "juni", "juli",
         "agustus", "september", "oktober", "november", "desember"]
_RE_DATE = re.compile(r"(?<![0-9A-Za-z])([0-9IlLO]{1,2})\s*([A-Za-z]{3,10})\s*,?\s*((?:19|20)\d{2})")
_RE_PERIOD = re.compile(
    r"(TAHUN PAJAK \d{4}"
    r"|MASA PAJAK [A-Z]+ (?:TAHUN )?\d{4}(?: SAMPAI DENGAN MASA PAJAK [A-Z]+ (?:TAHUN )?\d{4})?)"
)
_RE_PERIOD_CONTEXT = re.compile(
    r"(?:BERLAKU|DIBERIKAN|DITANGGUNG PEMERINTAH|DIBERLAKUKAN)\W+(?:\S+\W+){0,8}?(?:UNTUK|PADA|SEJAK)\W+$"
)
_RE_PARTIAL = re.compile(r"\b(PASAL|LAMPIRAN|BAGIAN|AYAT|BAB)\b")
_RE_ARTICLE_TITLE = re.compile(r"(?<=[\w)]{2}[.;]\s)PASAL\s+(?:\d+[A-Z]?|[IVX]+)\s+(?!AYAT|HURUF|ANGKA)")
_LEADING_TYPES = re.compile(
    r"(PERATURAN (?:MENTERI KEUANGAN|PEMERINTAH(?: PENGGANTI UNDANG-UNDANG)?|PRESIDEN|DIREKTUR JENDERAL PAJAK)"
    r"|KEPUTUSAN MENTERI KEUANGAN|UNDANG-UNDANG)(?: REPUBLIK INDONESIA)?(?: NOMOR)?\s*$"
)


def _month(word: str) -> int | None:
    k = word.lower()
    if k in MONTHS:
        return MONTHS.index(k) + 1
    match = difflib.get_close_matches(k, MONTHS, n=1, cutoff=0.6)
    return MONTHS.index(match[0]) + 1 if match else None


def parse_date(text: str) -> list[tuple[str, int, int]]:
    result = []
    for m in _RE_DATE.finditer(text):
        day_text = m.group(1).translate(str.maketrans("IlLO", "1110"))
        month = _month(m.group(2))
        if not day_text.isdigit() or month is None:
            continue
        try:
            d = _dt.date(int(m.group(3)), month, int(day_text))
        except ValueError:
            continue
        result.append((d.isoformat(), m.start(), m.end()))
    return result


@dataclass(frozen=True)
class Revocation:
    identitas: RegulationId
    sebagian: bool
    bagian: str = ""


@dataclass
class TextExtraction:
    in_force_from: str | None = None
    enacted: str | None = None
    promulgated: str | None = None
    applies_to: list[str] = field(default_factory=list)
    revokes: list[Revocation] = field(default_factory=list)
    amends: list[RegulationId] = field(default_factory=list)
    amends_intermediate: list[RegulationId] = field(default_factory=list)
    amended_articles: dict[RegulationId, list[str]] = field(default_factory=dict)
    unreadable: list[str] = field(default_factory=list)
    is_decree: bool = False
    chained_revocation: bool = False
    promulgated_metadata: str | None = None

    @property
    def mulai_berlaku_tanggal(self) -> str | None:
        if self.in_force_from == "diundangkan":
            return self.promulgated or self.promulgated_metadata
        return self.in_force_from

    @property
    def retroaktif(self) -> bool:
        reference = self.promulgated or self.promulgated_metadata or self.enacted
        if not reference:
            return False
        starts = [self.mulai_berlaku_tanggal] if self.mulai_berlaku_tanggal else []
        for p in self.applies_to:
            m = re.match(r"TAHUN PAJAK (\d{4})", p)
            if m:
                starts.append(f"{m.group(1)}-01-01")
            m = re.match(r"MASA PAJAK ([A-Z]+) (?:TAHUN )?(\d{4})", p)
            if m and _month(m.group(1)):
                starts.append(f"{m.group(2)}-{_month(m.group(1)):02d}-01")
        return any(a < reference for a in starts if a)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _body_end(t: str) -> int:
    positions = [m.start() for m in re.finditer(r"AGAR\s+SETIAP", t)]
    if positions:
        return positions[-1]
    signature = [m.start() for m in re.finditer(r"DITETAPKAN\s+DI\s+\S+\s+PADA\s+TANGGAL", t)]
    return signature[-1] if signature else len(t)


def extract(text: str, doc_id: RegulationId | None = None) -> TextExtraction:
    t = _normalize(text).upper()
    result = TextExtraction()
    end = _body_end(t)
    closing_start = max(t.rfind("KETENTUAN PENUTUP", 0, end), max(0, end - 6000))
    closing = t[closing_start:end]
    signature = t[end:end + 1500]
    result.is_decree = not re.search(r"AGAR\s+SETIAP", t)

    for key, attr, word in (("ditetapkan", "enacted", "DITETAPKAN"), ("diundangkan", "promulgated", "DIUNDANGKAN")):
        m = re.search(rf"{word}\s+DI\s+\S+\s+PADA\s+TANGGAL", signature)
        if m:
            dates = parse_date(signature[m.end():m.end() + 40])
            if dates:
                setattr(result, attr, dates[0][0])
        if getattr(result, attr) is None and not (key == "diundangkan" and result.is_decree):
            result.unreadable.append(key)

    occurrences = list(re.finditer(r"MULAI\s+BERLAKU", closing))
    if occurrences:
        m = occurrences[-1]
        after_text = closing[m.end():m.end() + 140]
        if "TANGGAL DIUNDANGKAN" in after_text[:60]:
            result.in_force_from = "diundangkan"
        else:
            after = parse_date(after_text)
            before = parse_date(closing[max(0, m.start() - 90):m.start()])
            range_match = re.match(r"\s*PADA\s+TANGGAL\s+(\d{1,2})\s+([A-Z]+)\s+SAMPAI\s+DENGAN", after_text)
            if range_match and after:
                range_start = parse_date(f"{range_match.group(1)} {range_match.group(2)} {after[0][0][:4]}")
                if range_start:
                    after = range_start + after
            if after:
                result.in_force_from = after[0][0]
            elif before:
                result.in_force_from = before[-1][0]
    if result.in_force_from is None:
        result.unreadable.append("mulai_berlaku")

    body = t[:end]
    for m in _RE_PERIOD.finditer(body):
        prefix = body[max(0, m.start() - 120):m.start()]
        if _RE_PERIOD_CONTEXT.search(prefix) and m.group(1) not in result.applies_to:
            result.applies_to.append(m.group(1))

    positions = [(i, a, b) for i, a, b in find_all_positions(closing) if i != doc_id]
    article_titles = [j.end() for j in _RE_ARTICLE_TITLE.finditer(closing)]
    left_bound = 0
    for m in re.finditer(r"DICABUT", closing):
        left = max([left_bound] + [j for j in article_titles if j < m.start()])
        anchor = closing.rfind("PADA SAAT", left, m.start())
        start = anchor if anchor >= 0 else max(left, m.start() - 1500)
        if re.search(r"SEBAGAIMANA\s+TELAH\s+(?:BEBERAPA\s+KALI\s+)?DIUBAH", closing[start:m.start()]):
            result.chained_revocation = True
        for ident, a, _ in positions:
            if not (start <= a < m.start()):
                continue
            prefix = closing[start:a]
            in_force = prefix.rfind("BERLAKU,")
            cut = max(prefix.rfind(";"), prefix.rfind(":"), in_force + len("BERLAKU,") - 1 if in_force >= 0 else -1)
            if cut >= 0:
                prefix = prefix[cut + 1:]
            prefix = re.sub(r"\b(?:I|L)?\s*(?:WWW\.)?JDIH\.KEMENKEU\.GO\.ID\s*(?:-\s*\d+\s*-)?\s*", " ", prefix)
            prefix = _LEADING_TYPES.sub("", prefix.strip()).strip(" ,")
            prefix = re.sub(r"^(?:DAN\s+)?(?:[A-Z]\.\s+)?", "", prefix).strip()
            partial = bool(_RE_PARTIAL.search(prefix))
            p = Revocation(ident, partial, prefix if partial else "")
            if all(x.identitas != ident for x in result.revokes):
                result.revokes.append(p)
        left_bound = m.end()

    for m in re.finditer(r"DIUBAH\s+SEBAGAI\s+BERIKUT", t[:end]):
        prefix = t[max(0, m.start() - 600):m.start()]
        k = list(re.finditer(r"KETENTUAN\s+DALAM\b", prefix))
        if k:
            prefix = prefix[k[-1].end():]
        intermediate = re.search(r"SEBAGAIMANA\s+TELAH\b", prefix)
        for ident, a, _ in find_all_positions(prefix):
            if ident == doc_id or ident in result.amends:
                continue
            result.amends.append(ident)
            if intermediate and a > intermediate.start():
                result.amends_intermediate.append(ident)
    for ident, articles in amended_articles(t[:end]).items():
        if ident in result.amends and ident not in result.amends_intermediate:
            result.amended_articles[ident] = articles
    return result


_RE_OPENING = re.compile(r"\bKETENTUAN\s+DALAM\s+(?=(?:PERATURAN|KEPUTUSAN|UNDANG-UNDANG)\b)")
_RE_ITEM = re.compile(r"(?:(?<=[\w)][.;]\s)|(?<=:\s))\d{1,3}\.\s+")
_RE_INSTRUCTION = re.compile(r"^(?:KETENTUAN|DI\s+ANTARA|PASAL|PENJELASAN|LAMPIRAN)\b")
_RE_ARTICLE = re.compile(r"\bPASAL\s+(\d+[A-Z]?)\b")


def amended_articles(body: str) -> dict[RegulationId, list[str]]:
    openings = []
    for m in _RE_OPENING.finditer(body):
        match = [(i, a) for i, a, _ in find_all_positions(body[m.end():m.end() + 200]) if a < 5]
        if match:
            openings.append((m.end(), match[0][0]))
    result: dict[RegulationId, list[str]] = {}
    for n, (start, ident) in enumerate(openings):
        stop = openings[n + 1][0] if n + 1 < len(openings) else len(body)
        region = body[start:stop]
        head = re.search(r"SEBAGAI\s+BERIKUT\s*:", region)
        if not head:
            continue
        region = ": " + region[head.end():].lstrip()
        articles: list[str] = []
        for b in _RE_ITEM.finditer(region):
            item = region[b.end():b.end() + 600]
            if not _RE_INSTRUCTION.match(item):
                continue
            cut = re.search(r"SEHINGGA|:", item)
            instruction = item[:cut.start()] if cut else item[:300]
            if not re.search(r"DIUBAH|DIHAPUS|DISISIPKAN|DITAMBAHKAN", instruction):
                continue
            instruction = re.sub(r"DI\s+ANTARA\s+PASAL\s+\w+\s+DAN\s+PASAL\s+\w+", " ", instruction)
            found = _RE_ARTICLE.findall(instruction)
            if not found and re.search(r"YAKNI\s+BAB\b", instruction) and cut:
                found = _RE_ARTICLE.findall(item[cut.end():cut.end() + 300])[:1]
            for p in found:
                if p not in articles:
                    articles.append(p)
        if articles:
            result.setdefault(ident, [])
            result[ident] += [p for p in articles if p not in result[ident]]
    return result
