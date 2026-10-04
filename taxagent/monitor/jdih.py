from __future__ import annotations

import html as _html
import json
import re
from dataclasses import dataclass, field
from urllib.parse import urlencode

from .identity import RegulationId, canon_id, from_slug

BASE_URL = "https://jdih.kemenkeu.go.id"

_RE_RELATION = re.compile(
    r'"KodeRelasi":"(?P<kode>[^"]*)"[^{}]*?"Nama":"(?P<nama>[^"]*)"'
    r'[^{}]*?"TglMulaiBerlaku":"(?P<tgl>[^"]*)"[^{}]*?"Nomor":"(?P<nomor>[^"]*)"'
    r'[^{}]*?"Slug":"(?P<slug>[^"]*)"'
)
_RE_DATE = {
    "penetapan": re.compile(r'"TglPenetapan":"\$D(\d{4}-\d{2}-\d{2})'),
    "pengundangan": re.compile(r'"TglPengundangan":"\$D(\d{4}-\d{2}-\d{2})'),
}
_RE_VALIDITY = re.compile(r'"TglPengundangan":"[^"]*","TglMulaiBerlaku":"([^"]*)","TglSelesaiBerlaku":"([^"]*)"')
_RE_LAST_HISTORY = re.compile(r'riwayat-badge riwayat-badge--\w+","children":"([^"]+)"\}\],'
                                  r'\["\$","span",null,\{"className":"riwayat-latest"')
_RE_TITLE = re.compile(r"<title>(.*?)</title>", re.S)
_RE_DOWNLOAD = re.compile(r'api/download/[^"\\\s<>]+')


@dataclass(frozen=True)
class Relation:
    kode: str
    nama: str
    arah: str
    jenis_efek: str
    nomor: str
    slug: str
    tgl_mulai_berlaku: str | None
    identitas: RegulationId | None


@dataclass
class JDIHPage:
    url: str
    nomor: str = ""
    judul: str = ""
    tgl_penetapan: str | None = None
    tgl_pengundangan: str | None = None
    tgl_mulai_berlaku: str | None = None
    tgl_selesai_berlaku: str | None = None
    riwayat_terakhir: str | None = None
    relasi: list[Relation] = field(default_factory=list)
    url_unduh: list[str] = field(default_factory=list)
    kunci_relasi: tuple[str, ...] = ()

    @property
    def identitas(self) -> RegulationId | None:
        return canon_id(self.nomor) if self.nomor else from_slug(self.url)


def _direction_and_type(name: str) -> tuple[str, str]:
    n = " ".join(name.lower().split())
    incoming = n.startswith(("dicabut", "diubah"))
    if "sebagian" in n:
        kind = "mencabut_sebagian"
    elif "cabut" in n:
        kind = "mencabut"
    elif "ubah" in n:
        kind = "mengubah"
    else:
        kind = "lain"
    return ("masuk" if incoming else "keluar"), kind


def _date(value: str) -> str | None:
    m = re.match(r"\$D(\d{4}-\d{2}-\d{2})", value)
    return m.group(1) if m else None


def parse_page(content: str, url: str = "") -> JDIHPage:
    data = content.replace('\\"', '"')
    page = JDIHPage(url=url)

    m = _RE_TITLE.search(content)
    if m:
        title = _html.unescape(m.group(1)).split("|")[0].strip()
        number, _, rest = title.partition(" - ")
        page.nomor, page.judul = number.strip(), rest.strip()
    for key, rx in _RE_DATE.items():
        t = rx.search(data)
        setattr(page, f"tgl_{key}", t.group(1) if t else None)
    m = _RE_VALIDITY.search(data)
    if m:
        page.tgl_mulai_berlaku, page.tgl_selesai_berlaku = _date(m.group(1)), _date(m.group(2))
    m = _RE_LAST_HISTORY.search(data)
    page.riwayat_terakhir = m.group(1).strip() if m else None

    seen = set()
    json_keys: set[str] = set()
    for r in _RE_RELATION.finditer(data):
        start = data.rfind("{", 0, r.start())
        json_keys.update(re.findall(r'"(\w+)":', data[start + 1 : r.end()]))
        key = (r["kode"], r["nama"].strip(), r["slug"])
        if key in seen:
            continue
        seen.add(key)
        direction, kind = _direction_and_type(r["nama"])
        page.relasi.append(
            Relation(
                kode=r["kode"],
                nama=" ".join(r["nama"].split()),
                arah=direction,
                jenis_efek=kind,
                nomor=r["nomor"],
                slug=r["slug"],
                tgl_mulai_berlaku=_date(r["tgl"]),
                identitas=canon_id(r["nomor"]) or from_slug(r["slug"]),
            )
        )

    page.kunci_relasi = tuple(sorted(json_keys))

    for u in dict.fromkeys(_RE_DOWNLOAD.findall(content)):
        if "/abtrak/" in u:
            continue
        page.url_unduh.append(f"{BASE_URL}/{u}")
    return page


def page_url(slug: str) -> str:
    return f"{BASE_URL}/dok/{slug}"


_RE_FLIGHT = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')


def item_listing(html: str) -> list[dict]:
    payload = "".join(json.loads(f'"{s}"') for s in _RE_FLIGHT.findall(html))
    decoder, result, i = json.JSONDecoder(), {}, 0
    while (i := payload.find('{"produk_hukum_id"', i)) != -1:
        try:
            obj, end = decoder.raw_decode(payload, i)
        except json.JSONDecodeError:
            i += 1
            continue
        result.setdefault(obj["produk_hukum_id"], obj)
        i = end
    return list(result.values())


def search_url(param: dict, page_no: int = 0) -> str:
    return f"{BASE_URL}/search?" + urlencode({"q": "", **param, "page": page_no})


def candidate_slugs(ident: RegulationId) -> list[str]:
    j, n, t = ident.kind.lower(), ident.number, ident.year
    if ident.kind in ("PER", "KEP", "SE"):
        return [f"{j}-{n}{(ident.issuer or '').lower()}{t}"]
    candidates = [f"{j}-{n}-tahun-{t}"]
    if ident.kind == "PMK" and ident.old_unit:
        candidates.insert(0, f"{n}-pmk-{ident.old_unit.split('.')[-1]}-{t}")
    return candidates
