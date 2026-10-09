from __future__ import annotations

import re

from .relation_evidence import NormText

_RE_CONSIDERING = re.compile(r"\bMENIMBANG\s*:?")
_RE_RECALLING = re.compile(r"\bMENGINGAT\s*:?")
_RE_END = re.compile(r"\bDENGAN PERSETUJUAN BERSAMA\b|\bMEMPERHATIKAN\s*:|\bMEMUTUSKAN\b|\bMENETAPKAN\s*:")
_RE_ARTICLE = re.compile(r"PASAL\s+(\d+[A-Z]?)")
_RE_AMENDED = re.compile(r"SEBAGAIMANA TELAH(?: BEBERAPA KALI)?(?: DIUBAH| BEBERAPA KALI DIUBAH)|TERAKHIR DENGAN|DIUBAH DENGAN")


def _items(s: str, a: int, b: int) -> list[tuple[int, int]]:
    result, start = [], a
    for m in re.finditer(";", s[a:b]):
        result.append((start, a + m.end()))
        start = a + m.end()
    if start < b:
        result.append((start, b))
    return result


def find_legal_basis(t: NormText, own_key: str) -> list[dict]:
    body_end = t.body_start or len(t.s)
    m_recall = _RE_RECALLING.search(t.s, 0, body_end)
    m_consider = _RE_CONSIDERING.search(t.s, 0, body_end)
    sections = []
    if m_consider:
        end = m_recall.start() if m_recall and m_recall.start() > m_consider.end() else body_end
        sections.append(("menimbang", m_consider.end(), end))
    if m_recall:
        end = _RE_END.search(t.s, m_recall.end(), body_end + 20)
        sections.append(("mengingat", m_recall.end(), end.start() if end else body_end))
    result: dict[tuple[str, str], dict] = {}
    order = 0
    for section, a, b in sections:
        for ba, bb in _items(t.s, a, b):
            mentions = sorted((x for x in t.mentions if ba <= x[1] < bb), key=lambda x: x[1])
            prev_end = ba
            for ident, sa, sb in mentions:
                k = str(ident)
                if k == own_key:
                    prev_end = sb
                    continue
                between = t.s[prev_end:sa]
                if section == "menimbang":
                    if not re.search(r"MELAKSANAKAN|DIMAKSUD DALAM|DIAMANATKAN|BERDASARKAN", t.s[ba:sa]):
                        prev_end = sb
                        continue
                    role = "delegasi"
                else:
                    role = "perubahan" if prev_end > ba and _RE_AMENDED.search(between) else "pokok"
                articles = sorted(set(_RE_ARTICLE.findall(between)), key=lambda p: (int(re.match(r"\d+", p).group()), p))
                entry_key = (k, section)
                if entry_key not in result:
                    order += 1
                    result[entry_key] = {"ke": k, "bagian": section, "peran": role, "urutan": order, "pasal": articles,
                                         "kutipan": t.quote(ba, bb)[:600]}
                else:
                    result[entry_key]["pasal"] = sorted(set(result[entry_key]["pasal"]) | set(articles))
                prev_end = sb
    return list(result.values())
