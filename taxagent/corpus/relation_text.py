from __future__ import annotations

import re
from collections.abc import Iterable

from ..monitor.identity import RegulationId
from .relation_evidence import RE_SENTENCE_END, NormText, article_before, articles_paragraphs, section_of, via_amender

_RE_VERB = re.compile(r"DICABUT DAN DINYATAKAN TIDAK BERLAKU|DINYATAKAN TIDAK BERLAKU(?: LAGI)?"
                      r"|DIUBAH SEBAGAI BERIKUT|DIUBAH SEHINGGA|DIUBAH DAN DITAMBAH")
_RE_NOT_TARGET = re.compile(r"(?:BERDASARKAN|SEBAGAIMANA DIMAKSUD (?:DALAM|PADA)|DALAM RANGKA MELAKSANAKAN"
                            r"|UNTUK MELAKSANAKAN|DITETAPKAN DENGAN|DIATUR DENGAN|DIATUR DALAM|SESUAI DENGAN"
                            r"|PERATURAN PELAKSANAAN(?: DARI)?)"
                            r"[^;,]{0,60}$")
_RE_IN_TITLE = re.compile(r"\bTENTANG\b(?:(?!\bDENGAN\b)[^;,]){0,60}$")
_RE_INSOFAR = re.compile(r"\bSEPANJANG\b")
_RE_PROVISION_IN = re.compile(r"\bKETENTUAN\b[^;]{0,600}\b(?:DALAM|PADA)\s+"
                              r"(?:(?:PERATURAN|KEPUTUSAN)[A-Z ]{0,60}?NOMOR\s*:?\s*)?$")
_RE_PERPPU_ENACTMENT = re.compile(r"PENETAPAN PERATURAN PEMERINTAH PENGGANTI UNDANG-?\s?UNDANG NOMOR (\d{1,4}) "
                                  r"TAHUN (\d{4})")
_RE_HAS_REGULATION = re.compile(r"PERATURAN|KEPUTUSAN|UNDANG|SURAT EDARAN")
_RE_ACTIVE_AMEND = re.compile(r"\bMENGUBAH\s+(?:BEBERAPA\s+)?(?:KETENTUAN|LAMPIRAN|PASAL|ANGKA|HURUF|BUTIR)\b")
_RE_ACTIVE_OPENING = re.compile(r"(?:\bPASAL [IVX]+|\bKESATU|\bPERTAMA|:)\s*$")
_RE_ACTIVE_END = re.compile(r":|SEBAGAI BERIKUT|SEHINGGA")
_RE_INSTRUCTION = re.compile(
    r"(?:^|[\s:;\"”])\d{1,3}\.\s+(?:KETENTUAN\b(?P<ubah>[^.]{0,200}?)\b(?:DIUBAH|DIHAPUS|DITAMBAH)"
    r"|DI ANTARA\b[^.]{0,200}?\bDISISIPKAN\b(?P<sisip>[^.]{0,200}?)(?:SEHINGGA|BERBUNYI|:)"
    r"|(?P<hapus>PASAL \d+[A-Z]? DIHAPUS))")
_RE_INSTRUCTION_END = re.compile(r"\bPASAL [IVX]+\b(?! AYAT)|BEBERAPA KETENTUAN DALAM|\bMENGUBAH BEBERAPA")


def amended_articles(t: NormText, start: int, end: int) -> list[str]:
    stop = _RE_INSTRUCTION_END.search(t.s, start, end)
    seg = t.s[start:stop.start() if stop else min(end, start + 300000)]
    result: list[str] = []
    for m in _RE_INSTRUCTION.finditer(seg):
        body = m.group("ubah") or m.group("sisip") or m.group("hapus") or ""
        for p in re.findall(r"PASAL\s+(\d+[A-Z]?)\b", body):
            if p not in result:
                result.append(p)
    return sorted(result, key=lambda p: (int(re.match(r"\d+", p).group()), p))


_RE_CLAUSE_START = re.compile(r"(?<!, )(?<!DAN )\bBAB [IVXLC]+\b(?! (?:PERATURAN|UNDANG|KEPUTUSAN|SAMPAI|DAN)\b)"
                              r"|\bPASAL \d+[A-Z]? (?=PADA SAAT|DENGAN BERLAKUNYA)")


def _sentence_start(t: NormText, pos: int) -> int:
    start = t.body_start
    for m in RE_SENTENCE_END.finditer(t.s, max(t.body_start, pos - 6000), pos):
        start = m.end()
    for m in _RE_CLAUSE_START.finditer(t.s, max(start, pos - 6000), pos):
        start = m.start()
    return max(start, pos - 6000)


def find_relations(t: NormText, own_key: str, doc_type: str = "") -> tuple[list[dict], list[dict]]:
    found: dict[tuple[str, str], dict] = {}
    leftover: list[dict] = []
    end = t.s.find("AGAR SETIAP ORANG MENGETAHUINYA", t.body_start)
    end = end if end != -1 else len(t.s)

    def keep(k: str, rel: dict) -> None:
        old = found.get((k, rel["jenis"]))
        if old is None or (old["kelas"] == "tersirat" and rel["kelas"] == "eksplisit"):
            found[(k, rel["jenis"])] = rel
        elif rel.get("pasal_terdampak") and not old.get("pasal_terdampak"):
            old["pasal_terdampak"] = rel["pasal_terdampak"]

    for v in _RE_VERB.finditer(t.s, t.body_start, end):
        kind = "mengubah" if v.group(0).startswith("DIUBAH") else "mencabut"
        a0 = _sentence_start(t, v.start())
        matched = False
        for ident, a, b in t.mentions:
            if not (a0 <= a < v.start()):
                continue
            k = str(ident)
            before = t.s[max(a0, a - 120):a]
            if k == own_key or _RE_NOT_TARGET.search(before) or _RE_IN_TITLE.search(before):
                continue
            item = t.s[max(a0, t.s.rfind(";", a0, a) + 1):a]
            own_article = (article_before(t, a) or "").removeprefix("Pasal ")
            articles = articles_paragraphs(item, own_article)
            semicolon = t.s.find(";", b, v.start())
            insofar = bool(_RE_INSOFAR.search(t.s, b, semicolon if semicolon != -1 else v.start())
                           or _RE_PROVISION_IN.search(item))
            j = "mencabut_sebagian" if kind == "mencabut" and (articles or insofar) else kind
            base = via_amender(t, a)
            rel = {"ke": k, "jenis": j, "kelas": "tersirat" if base and base != k else "eksplisit",
                   "kutipan": t.quote(a0, v.end())[-1500:], "pasal": article_before(t, a), "bagian": section_of(t, a),
                   "offset": list(t.offset(a, b)), "pasal_terdampak": articles if j == "mencabut_sebagian" else None}
            if insofar and not articles and j == "mencabut_sebagian":
                rel["catatan"] = "dicabut sepanjang mengatur hal tertentu (pasal tidak disebut)"
            if rel["kelas"] == "tersirat":
                rel["lewat"] = base
            elif j == "mengubah":
                rel["pasal_terdampak"] = amended_articles(t, v.end(), end) or None
            matched = True
            keep(k, rel)
        sentence = t.s[a0:v.start()]
        if (not matched and _RE_HAS_REGULATION.search(sentence)
                and not re.search(r"KETENTUAN (?:PASAL|AYAT|HURUF|ANGKA|PENJELASAN|LAMPIRAN)|YANG BERTENTANGAN",
                                  sentence)):
            leftover.append({"kalimat": t.quote(a0, v.end())[-800:], "jenis": kind, "offset": list(t.offset(a0, v.end()))})
    for m in _RE_ACTIVE_AMEND.finditer(t.s, t.body_start, end):
        if not _RE_ACTIVE_OPENING.search(t.s[max(t.body_start, m.start() - 40):m.start()]):
            continue
        stop = _RE_ACTIVE_END.search(t.s, m.end(), min(end, m.end() + 800))
        if stop is None:
            continue
        articles, first = None, True
        for ident, a, b in t.mentions:
            if not (m.end() <= a < stop.start()):
                continue
            k = str(ident)
            if k == own_key:
                continue
            base = via_amender(t, a)
            if not first and not (base and base != k):
                continue
            first = False
            rel = {"ke": k, "jenis": "mengubah", "kelas": "tersirat" if base and base != k else "eksplisit",
                   "kutipan": t.quote(m.start(), stop.end())[-1500:], "pasal": article_before(t, a),
                   "bagian": section_of(t, a), "offset": list(t.offset(a, b)), "pasal_terdampak": None}
            if rel["kelas"] == "tersirat":
                rel["lewat"] = base
            else:
                articles = articles if articles is not None else (amended_articles(t, stop.end(), end) or None)
                rel["pasal_terdampak"] = articles
            keep(k, rel)
    if doc_type.upper().startswith(("UNDANG", "UU")):
        m = _RE_PERPPU_ENACTMENT.search(t.s[:t.body_start + 3000])
        if m:
            k = str(RegulationId("PERPPU", int(m.group(1)), int(m.group(2))))
            found[(k, "ditetapkan_menjadi")] = {"ke": k, "jenis": "ditetapkan_menjadi", "kelas": "eksplisit",
                                                "arah": "masuk", "kutipan": t.quote(m.start(), m.end()),
                                                "pasal": "Judul", "bagian": "judul",
                                                "offset": list(t.offset(m.start(), m.end())), "pasal_terdampak": None}
    return list(found.values()), leftover


def pajak_status(pajak_keys: Iterable[tuple[str, str | None]], revoked_in: set[str]) -> list[dict]:
    out = []
    for k, label in pajak_keys:
        revoked_by_text = k in revoked_in
        if label == "Dicabut" and not revoked_by_text:
            out.append({"kunci": k, "label_pajak": label, "status": "dicabut", "sumber": "status_pajak_go_id"})
        elif label == "Aktif" and revoked_by_text:
            out.append({"kunci": k, "label_pajak": label, "status": "dicabut", "sumber": "teks",
                        "konflik": "label pajak.go.id Aktif, teks peraturan lain mencabutnya"})
        elif label == "Dicabut" and revoked_by_text:
            out.append({"kunci": k, "label_pajak": label, "status": "dicabut", "sumber": "teks"})
    return out
