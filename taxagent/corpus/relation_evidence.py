from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict
from dataclasses import dataclass, field

from ..monitor.identity import RegulationId, canon_id, find_all_positions

VERBS = {"mencabut": r"DICABUT|TIDAK BERLAKU", "mencabut_sebagian": r"DICABUT|TIDAK BERLAKU|DIHAPUS",
         "mengubah": r"DIUBAH|PERUBAHAN|DISISIPKAN|DITAMBAHKAN",
         "ditetapkan_menjadi": r"DITETAPKAN MENJADI|MENETAPKAN .{0,200}MENJADI UNDANG"}
WINDOW = 900
LIST_WINDOW = 20000
_RE_ARTICLE = re.compile(r"(?<![a-z] )(?<![a-z],)\b(?:Pasal|PASAL)\s+([IVX]+|\d+[A-Z]?)\s+(?=[A-Z]|[a-z]\. )")
_RE_LIST_NUMBER = re.compile(r"(?<=[;:] )[A-Z]\. NOMOR\s*(\d{1,4})\s*TAHUN\s*(\d{4})")
_RE_LIST_TITLE = re.compile(r"(UNDANG-?\s?UNDANG|PERATURAN PEMERINTAH(?! PENGGANTI)|PERATURAN PRESIDEN"
                            r"|KEPUTUSAN PRESIDEN)\s*:")
_LIST_TYPES = {"UNDANG": "UU", "PERATURAN PEMERINTAH": "PP", "PERATURAN PRESIDEN": "PERPRES",
               "KEPUTUSAN PRESIDEN": "KEPPRES"}


def _list_items(s: str) -> list[tuple[RegulationId, int, int]]:
    result = []
    for x in _RE_LIST_NUMBER.finditer(s):
        titles = list(_RE_LIST_TITLE.finditer(s, max(0, x.start() - 3000), x.start()))
        if not titles:
            continue
        name = titles[-1].group(1)
        kind = next(v for k, v in _LIST_TYPES.items() if name.startswith(k))
        result.append((RegulationId(kind, int(x.group(1)), int(x.group(2))), x.start(), x.end()))
    return result
_RE_AS_AMENDED = re.compile(r"SEBAGAIMANA\s+TELAH\s+(?:BEBERAPA\s+KALI\s+|DUA\s+KALI\s+)?DIUBAH")
_MONTHS = {b: i for i, b in enumerate(["JANUARI", "FEBRUARI", "MARET", "APRIL", "MEI", "JUNI", "JULI", "AGUSTUS",
                                       "SEPTEMBER", "OKTOBER", "NOVEMBER", "DESEMBER"], 1)}


@dataclass
class NormText:
    raw: str
    s: str
    s_cased: str
    offset_map: list[int]
    body_start: int
    mentions: list[tuple[RegulationId, int, int]] = field(default_factory=list)

    @classmethod
    def from_raw(cls, raw: str) -> NormText:
        out, cased, index_map, in_space = [], [], [], False
        for i, c in enumerate(raw):
            if c.isspace():
                if not in_space:
                    out.append(" ")
                    cased.append(" ")
                    index_map.append(i)
                in_space = True
                continue
            in_space = False
            u = c.upper()
            out.append(u if len(u) == 1 else c)
            cased.append(c)
            index_map.append(i)
        s = "".join(out)
        s = re.sub(r"(?<=\d)O|O(?=\d)", "0", s)
        s = re.sub(r"(?<=\d)[IL](?=[\d/.])|(?<=[\s/.])[IL](?=\d)", "1", s)
        m = re.search(r"\bMEMUTUSKAN\b", s) or re.search(r"\bMENETAPKAN\s*:", s)
        t = cls(raw, s, "".join(cased), index_map, m.end() if m else 0)
        t.mentions = find_all_positions(s)
        t.mentions += _list_items(s)
        return t

    def offset(self, a: int, b: int) -> tuple[int, int]:
        return self.offset_map[a], self.offset_map[min(b, len(self.offset_map)) - 1] + 1

    def quote(self, a: int, b: int) -> str:
        x, y = self.offset(a, b)
        return " ".join(self.raw[x:y].split())


def article_before(t: NormText, pos: int) -> str | None:
    p = [x.group(1) for x in _RE_ARTICLE.finditer(t.s_cased, max(0, pos - 20000), pos)]
    return f"Pasal {p[-1]}" if p else None


def section_of(t: NormText, pos: int) -> str:
    attachment = t.s.find("LAMPIRAN", t.body_start)
    closing = t.s.find("AGAR SETIAP ORANG MENGETAHUINYA", t.body_start)
    if attachment != -1 and closing != -1 and pos > max(attachment, closing):
        return "lampiran"
    if re.search(r"PASAL\s+I\b", t.s[max(0, pos - 600):pos]):
        return "pasal_I"
    return "penutup" if "KETENTUAN PENUTUP" in t.s[max(t.body_start, pos - 3000):pos] else "batang_tubuh"


def _direct_evidence(t: NormText, target: RegulationId, kind: str) -> dict | None:
    candidates = []
    verbs = VERBS.get(kind, VERBS["mencabut"])
    for ident, a, b in t.mentions:
        if ident != target or a < t.body_start:
            continue
        position = round(a / len(t.s), 2)
        k = re.search(verbs, t.s[b:b + WINDOW])
        if k:
            start = max(t.s.rfind(". ", 0, a), t.s.rfind(": ", 0, a), a - 600)
            titles = list(_RE_ARTICLE.finditer(t.s_cased, max(0, a - 600), a))
            if titles:
                start = min(start, titles[-1].start() - 1)
            stop = t.s.find(".", b + k.end())
            stop = stop if stop != -1 and stop - b < 1500 else b + k.end() + 40
            sb = t.s.find("SEBAGAI BERIKUT", b, b + 1500)
            if kind == "mengubah" and sb != -1:
                stop = sb + len("SEBAGAI BERIKUT")
            candidates.append({"jarak": k.start(), "a": start + 1, "b": stop + 1, "sebut": (a, b), "posisi": position,
                               "bagian": section_of(t, a), "pasal": article_before(t, a)})
            continue
        if kind == "mengubah" and re.search(r"PERUBAHAN\s+(?:\w+\s+)?ATAS[^.]{0,60}$", t.s[max(0, a - 160):a]):
            start = max(t.s.rfind("MENETAPKAN", 0, a), a - 300)
            candidates.append({"jarak": 0, "a": start, "b": t.s.find(". ", b) + 1, "sebut": (a, b), "posisi": position,
                               "bagian": "judul", "pasal": "Menetapkan (judul)"})
            continue
        far = re.search(verbs, t.s[b:b + LIST_WINDOW])
        if far and re.search(r"; (?:DAN )?[A-Z]{1,2}\. ", t.s[b:b + far.start()]):
            start = max(t.s.rfind("; ", 0, a), t.s.rfind(": ", 0, a), a - 300) + 2
            candidates.append({"jarak": 5000, "a": start, "b": t.s.find(".", b + far.end()) + 1, "sebut": (a, b),
                               "posisi": position, "bagian": "daftar", "pasal": article_before(t, a),
                               "daftar": (b + far.start(), t.s.find(".", b + far.end()) + 1)})
    if not candidates:
        return None
    direction = 1 if kind == "mengubah" else -1
    c = min(candidates, key=lambda c: (c["pasal"] is None, c["jarak"] > 600, direction * c["posisi"]))
    if "daftar" in c:
        item_end = t.s.find(";", c["sebut"][1])
        quote_text = f"{t.quote(c['a'], item_end)} [...] {t.quote(*c['daftar'])}"
    else:
        quote_text = t.quote(c["a"], c["b"])
    affected = None
    if kind == "mencabut_sebagian":
        own = (c["pasal"] or "").removeprefix("Pasal ")
        affected = articles_paragraphs(t.s[c["a"]:c["sebut"][0]], own)
    return {"kutipan": quote_text[:1500], "pasal": c["pasal"], "bagian": c["bagian"],
            "offset": list(t.offset(*c["sebut"])), "pasal_terdampak": affected, "_sebut": c["sebut"][0]}


_RE_AMENDED_BY = re.compile(r"(?:SEBAGAIMANA|YANG)\s+(?:TELAH\s+)?(?:[A-Z]+\s+KALI\s+)?DIUBAH"
                            r"(?:\s+[A-Z]+\s+KALI)?(?:\s+TERAKHIR)?\s+DENGAN")
_RE_NEW_ITEM = re.compile(r";\s*(?:DAN\s+)?(?:(?:[A-Z]|\d{1,2})[.)]\s*)?(?:PERATURAN|KEPUTUSAN|UNDANG|INSTRUKSI"
                          r"|SURAT EDARAN)")
RE_SENTENCE_END = re.compile(r"(?<![\s;:][A-Z])(?<![\s;:][A-Z]\s)(?<![\s;:]\d)(?<![\s;:]\d\d)\.\s(?=[A-Z])")


def via_amender(t: NormText, a: int) -> str | None:
    found = list(_RE_AMENDED_BY.finditer(t.s, max(0, a - 1500), a))
    m = found[-1] if found else None
    if m is None or RE_SENTENCE_END.search(t.s, m.end(), a) or _RE_NEW_ITEM.search(t.s, m.end(), a):
        return None
    if a - m.end() > 400 and ":" not in t.s[m.end():m.end() + 80]:
        return None
    b = next((y for _, x, y in t.mentions if x == a), a)
    heading = re.match(r"\s*TENTANG\s+(\S+)", t.s[b:b + 60])
    if heading and not heading.group(1).startswith(("PERUBAHAN", "PENETAPAN")):
        return None
    base = [i for i, x, _ in t.mentions if m.start() - 600 < x < m.start()]
    return str(base[-1]) if base else None


def article_sort_key(p: str) -> tuple[int, str]:
    m = re.match(r"(\d+)(.*)", p)
    return (int(m.group(1)), m.group(2)) if m else (0, p)


_RE_ARTICLE_PARAGRAPH = re.compile(r"PASAL\s+(\d+[A-Z]?)"
                                   r"((?:\s*(?:,|DAN|SERTA)?\s*AYAT\s*\(\s*\d+[A-Z]?\s*\)"
                                   r"(?:\s*(?:,|DAN|SERTA)\s*\(\s*\d+[A-Z]?\s*\))*)*)")
_RE_REFERRED = re.compile(r"DIMAKSUD (?:DALAM|PADA) (?:AYAT\s*\(\s*\d+[A-Z]?\s*\)\s*)?$")
_RE_REGULATION_NAME = re.compile(r"\s*(?:PERATURAN|UNDANG|KEPUTUSAN)\b")


def articles_paragraphs(item: str, skip: str = "") -> list[str]:
    result: set[str] = set()
    for m in _RE_ARTICLE_PARAGRAPH.finditer(item):
        if m.group(1) == skip:
            continue
        if _RE_REFERRED.search(item, 0, m.start()) and not _RE_REGULATION_NAME.match(item, m.end()):
            continue
        paras = re.findall(r"\(\s*(\d+[A-Z]?)\s*\)", m.group(2))
        result |= {f"{m.group(1)}({a})" for a in paras} if paras else {m.group(1)}
    return sorted(result, key=article_sort_key)


def evidence(t: NormText, target_key: str, kind: str, parents: dict[str, set[str]] | None = None) -> dict:
    target = canon_id(target_key)
    if target is None:
        return {"kelas": "tanpa_bukti", "catatan": "kunci target tak terbaca"}
    result = _direct_evidence(t, target, kind)
    if result:
        pos = result.pop("_sebut")
        base = via_amender(t, pos)
        if base and base != target_key:
            return {"kelas": "tersirat", "lewat": base, **result}
        return {"kelas": "eksplisit", **result}
    for y in sorted(_ancestors(target_key, parents or {})):
        yi = canon_id(y)
        hy = _direct_evidence(t, yi, kind) if yi else None
        if hy and (_RE_AS_AMENDED.search(hy["kutipan"].upper()) or kind == "mengubah"):
            hy.pop("_sebut")
            return {"kelas": "tersirat", "lewat": y, **hy}
    return {"kelas": "tanpa_bukti"}


def _ancestors(k: str, parents: dict[str, set[str]], depth: int = 3) -> set[str]:
    result, frontier = set(), {k}
    for _ in range(depth):
        frontier = {y for x in frontier for y in parents.get(x, ())} - result
        result |= frontier
    return result


def parents_from_claims(claims: list[dict]) -> dict[str, set[str]]:
    parents: dict[str, set[str]] = defaultdict(set)
    for k in claims:
        if k["jenis"] == "mengubah":
            parents[k["dari"]].add(k["ke"])
    return parents


def effective_date(t: NormText, promulgated: str | None, enacted: str | None) -> tuple[str | None, str]:
    stop = t.s.find("AGAR SETIAP ORANG MENGETAHUINYA", t.body_start)
    body = t.s[t.body_start:stop if stop != -1 else len(t.s)]
    found = list(re.finditer(r"MULAI BERLAKU (PADA|SEJAK|SETELAH)(.{0,160})", body))
    if not found:
        return None, "tidak_terekstrak"
    m = found[-1]
    clause = re.split(r"\.\s+[A-Z]", m.group(1) + m.group(2))[0]
    x = re.search(r"SETELAH (\d+) .{0,40}?HARI .{0,40}?DIUNDANGKAN", clause)
    if x:
        if not promulgated:
            return None, "tidak_terekstrak"
        return (dt.date.fromisoformat(promulgated) + dt.timedelta(days=int(x.group(1)))).isoformat(), "n_hari"
    x = re.search(r"TANGGAL (\d{1,2}) (\w+) (\d{4})", clause)
    if x and x.group(2) in _MONTHS:
        try:
            return dt.date(int(x.group(3)), _MONTHS[x.group(2)], int(x.group(1))).isoformat(), "eksplisit"
        except ValueError:
            return None, "tidak_terekstrak"
    if "DIUNDANGKAN" in clause:
        return promulgated, "diundangkan" if promulgated else "tidak_terekstrak"
    if "DITETAPKAN" in clause:
        return enacted, "ditetapkan" if enacted else "tidak_terekstrak"
    return None, "tidak_terekstrak"
