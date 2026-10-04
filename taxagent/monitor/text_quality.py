from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from ..update.amounts import clean_text

_RE_WORD = re.compile(r"\w+", re.U)
SMALL_DIFF = 4
SCORE_THRESHOLD = 0.5
FULL_COVERAGE = 0.8


def words(text: str) -> list[tuple[str, int, int]]:
    return [(m.group(0).lower(), m.start(), m.end()) for m in _RE_WORD.finditer(text or "")]


class Corpus:
    def __init__(self, texts: list[str]):
        self.frek = Counter(k for t in texts for k, _, _ in words(t))

    def without(self, *texts: str) -> Counter:
        f = Counter(self.frek)
        for t in texts:
            f.subtract(Counter(k for k, _, _ in words(t)))
        return f


def _score(tokens: list[str], freq: Counter) -> float:
    return sum(math.log(max(freq.get(t, 0), 0) + 1) for t in tokens) / max(1, len(tokens))


def decide(a: list[str], b: list[str], freq: Counter) -> str:
    if "".join(a) == "".join(b):
        return "spasi"
    sa, sb = _score(a, freq), _score(b, freq)
    verdict = "pajak" if sa > sb + SCORE_THRESHOLD else "pdf" if sb > sa + SCORE_THRESHOLD else "ragu"
    if verdict == "pdf" and not (len(a) == len(b) == 1 and len(a[0]) >= 3 and len(b[0]) >= 3):
        return "ragu"
    return verdict


@dataclass
class Diff:
    pajak: str
    pdf: str
    verdict: str
    context: str = ""
    position: int = 0
    differing_numbers: bool = False


@dataclass
class Comparison:
    pajak_words: int
    pdf_words: int
    matches: int
    differences: list[Diff] = field(default_factory=list)
    best_text: str = ""

    @property
    def cakupan_pajak(self) -> float:
        return self.matches / self.pajak_words if self.pajak_words else 0.0

    @property
    def cakupan_pdf(self) -> float:
        return self.matches / self.pdf_words if self.pdf_words else 0.0

    def count(self) -> Counter:
        return Counter(b.verdict for b in self.differences)

    def errors_per_1000(self, side: str) -> float:
        other = "pdf" if side == "pajak" else "pajak"
        return 1000 * self.count()[other] / self.matches if self.matches else 0.0


def _pure_numbers(token: list[str]) -> bool:
    return bool(token) and all(t.isdigit() for t in token)


def compare(pajak_text: str, pdf_text: str, freq: Counter, base: str = "pajak") -> Comparison:
    ka, kb = words(pajak_text), words(pdf_text)
    ta, tb = [k for k, _, _ in ka], [k for k, _, _ in kb]
    sm = SequenceMatcher(None, ta, tb, autojunk=False)
    h = Comparison(len(ta), len(tb), sum(x.size for x in sm.get_matching_blocks()))
    replacements: list[tuple[int, int, str]] = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op != "replace" or (i2 - i1) > SMALL_DIFF or (j2 - j1) > SMALL_DIFF:
            continue
        a, b = ta[i1:i2], tb[j1:j2]
        start, end = ka[i1][1], ka[i2 - 1][2]
        context = pajak_text[max(0, start - 60):end + 60].replace("\n", " ")
        verdict = decide(a, b, freq)
        numeric_diff = _pure_numbers(a) and _pure_numbers(b)
        h.differences.append(Diff(" ".join(a), " ".join(b), verdict, context, start, numeric_diff))
        if numeric_diff:
            continue
        if base == "pajak" and verdict == "pdf":
            replacements.append((start, end, pdf_text[kb[j1][1]:kb[j2 - 1][2]]))
        elif base == "pdf" and verdict == "pajak":
            replacements.append((kb[j1][1], kb[j2 - 1][2], pajak_text[start:end]))
    frame = pajak_text if base == "pajak" else pdf_text
    parts, pos = [], 0
    for start, end, replacement in replacements:
        parts += [frame[pos:start], replacement]
        pos = end
    h.best_text = "".join(parts) + frame[pos:]
    return h


@dataclass
class InternalCheck:
    digit_mismatches: int
    verified_numbers: int
    foreign_chars: int
    has_enactment: bool
    has_promulgation: bool


def internal_check(text: str) -> InternalCheck:
    b = clean_text(text or "")
    lower = " ".join((text or "").lower().split())
    foreign = sum(1 for ch in text or "" if ch.isalpha() and not ("a" <= ch.lower() <= "z"))
    return InternalCheck(len(b.mismatches), len(b.verified), foreign,
                       "ditetapkan di" in lower, "diundangkan di" in lower)


@dataclass
class TextAssessment:
    document: str
    has_pajak: bool
    has_pdf: bool
    pdf_kind: str | None = None
    basis: str = "tidak_ada"
    best_text: str = ""
    comparison: Comparison | None = None
    internal_pajak: InternalCheck | None = None
    internal_pdf: InternalCheck | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def sumber_utama(self) -> str:
        return self.basis


def assess(document: str, pajak_text: str | None, pdf_text: str | None, corpus: Corpus,
          pdf_type: str | None = None) -> TextAssessment:
    p = TextAssessment(document, bool(pajak_text), bool(pdf_text), pdf_type)
    if pajak_text:
        p.internal_pajak = internal_check(pajak_text)
    if pdf_text:
        p.internal_pdf = internal_check(pdf_text)
    if pajak_text and pdf_text:
        freq = corpus.without(pajak_text)
        b = compare(pajak_text, pdf_text, freq)
        if b.cakupan_pajak < FULL_COVERAGE:
            p.notes.append(f"PDF hanya memuat {b.cakupan_pajak:.0%} isi pajak.go.id (PDF sebagian atau versi lain): "
                             "dasar pajak.go.id")
            p.basis, p.best_text = "pajak_pdf_sebagian", b.best_text
        elif pdf_type in ("ocr", "digital", None) and not _jdih_much_worse(b):
            b = compare(pajak_text, pdf_text, freq, base="pdf")
            p.basis = {"ocr": "jdih_ocr", "digital": "jdih_digital", None: "jdih_htm"}[pdf_type]
            p.best_text = b.best_text
        elif pdf_type in ("ocr", "digital", None):
            p.notes.append(f"teks JDIH terukur jauh lebih buruk ({b.errors_per_1000('pdf'):.1f} vs "
                             f"{b.errors_per_1000('pajak'):.1f} salah/1.000 kata): dasar pajak.go.id")
            p.basis, p.best_text = "pajak_dikoreksi_jdih", b.best_text
        else:
            p.basis, p.best_text = "pajak_dikoreksi_jdih", b.best_text
        p.comparison = b
        if b.cakupan_pdf < FULL_COVERAGE:
            p.notes.append(f"pajak.go.id hanya memuat {b.cakupan_pdf:.0%} isi PDF (lampiran/penjelasan hanya dari PDF)")
        n_numeric = sum(1 for x in b.differences if x.differing_numbers)
        if n_numeric:
            p.notes.append(f"{n_numeric} beda angka antara pajak.go.id dan PDF: tidak dikoreksi otomatis")
    elif pdf_text:
        p.basis, p.best_text = "jdih", pdf_text
        p.notes.append("teks pajak.go.id tidak ada: PDF tidak bisa dicek silang")
    elif pajak_text:
        p.basis, p.best_text = "pajak", pajak_text
        p.notes.append("PDF resmi tidak tersedia: teks tidak bisa dicek silang (satu sumber)")
    for name, c in (("pajak.go.id", p.internal_pajak), ("PDF", p.internal_pdf)):
        if c and c.digit_mismatches:
            p.notes.append(f"{name}: {c.digit_mismatches} angka digitnya tidak cocok dengan terbilang")
        if c and c.foreign_chars > 5:
            p.notes.append(f"{name}: {c.foreign_chars} huruf non-Latin (glyph tanda tangan elektronik/encoding)")
    return p


IMAGE_PAGE_THRESHOLD = 0.6
MAX_JDIH_ERRORS = 5.0


def _jdih_much_worse(b: Comparison) -> bool:
    jd, pj = b.errors_per_1000("pdf"), b.errors_per_1000("pajak")
    return jd > MAX_JDIH_ERRORS and jd > 2 * pj


def pdf_kind(content: bytes) -> str | None:
    if content.lstrip()[:5] != b"%PDF-":
        return None
    import pymupdf

    with pymupdf.open(stream=content, filetype="pdf") as doc:
        scan = 0
        for page in doc:
            area = page.rect.width * page.rect.height
            scan += any(r.width * r.height >= IMAGE_PAGE_THRESHOLD * area
                        for img in page.get_images(full=True) for r in page.get_image_rects(img[0]))
        return "scan" if doc.page_count and scan * 2 >= doc.page_count else "digital"


def jdih_pdf_text(ident, fetch) -> tuple[str | None, str | None, str | None]:
    from .enrichment import choose_text_url, page_from_id, text_from_file

    found = page_from_id(ident, fetch) if ident else None
    if not found:
        return None, "halaman JDIH tidak ditemukan", None
    _, page = found
    url = choose_text_url(page)
    if not url:
        return None, "halaman JDIH tanpa tautan teks", None
    content = fetch(url)
    return text_from_file(content, url), url, pdf_kind(content)
