from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

from ..monitor.identity import canon_id, from_slug
from .merge import normalize_number

STATUS_TYPES = ("mencabut", "mencabut_sebagian", "mengubah")
OTHER_RELATIONS = {
    "Ditetapkan Menjadi Undang-Undang": ("ditetapkan_menjadi", True),
    "Menetapkan Menjadi Undang-Undang": ("ditetapkan_menjadi", False),
    "Perpanjangan": ("memperpanjang", True),
    "Diperpanjang dengan": ("memperpanjang", False),
    "Pengaturan lebih lanjut": ("mengatur_lebih_lanjut", True),
    "Diatur lebih lanjut dengan": ("mengatur_lebih_lanjut", False),
    "Ditinjau dengan": ("meninjau", False),
}


@dataclass
class Claim:
    dari: str
    jenis: str
    ke: str
    dari_id: str | None = None
    ke_id: str | None = None
    ke_stub: bool = False
    nomor_mentah: list[str] = field(default_factory=list)
    tgl_mulai_berlaku: list[str] = field(default_factory=list)
    dicatat_di: list[str] = field(default_factory=list)

    @property
    def one_sided(self) -> bool:
        return len(self.dicatat_di) < 2

    def to_dict(self) -> dict:
        return {"dari": self.dari, "jenis": self.jenis, "ke": self.ke, "dari_id": self.dari_id,
                "ke_id": self.ke_id, "ke_stub": self.ke_stub, "nomor_mentah": self.nomor_mentah,
                "tgl_mulai_berlaku": self.tgl_mulai_berlaku, "dicatat_di": self.dicatat_di,
                "satu_sisi": self.one_sided}


def _slug(url_or_slug: str | None) -> str:
    return (url_or_slug or "").strip().strip("/").rsplit("/", 1)[-1].lower()


def target_key(r: dict, slug_to_id: dict[str, str], doc_keys: dict[str, str]) -> tuple[str | None, str | None]:
    i = slug_to_id.get(_slug(r.get("slug")))
    if i and doc_keys.get(i):
        return doc_keys[i], i
    ident = canon_id(normalize_number(r.get("nomor") or "")) or (from_slug(r["slug"]) if r.get("slug") else None)
    return (str(ident) if ident else None), i


def collect(pages: Iterable[tuple[str, dict]], doc_keys: dict[str, str]) -> tuple[list[Claim], dict]:
    pages = list(pages)
    slug_to_id = {_slug(d.get("url")): i for i, d in pages if d.get("url")}
    claims: dict[tuple[str, str, str], Claim] = {}
    stats: Counter = Counter()
    unreadable: list[str] = []
    self_refs: list[str] = []
    for i, d in pages:
        source = doc_keys.get(i) or (str(x) if (x := from_slug(_slug(d.get("url")))) else None)
        for r in d.get("relasi", []):
            stats["baris"] += 1
            if r.get("jenis_efek") in STATUS_TYPES:
                kind, outgoing = r["jenis_efek"], r.get("arah") == "keluar"
            elif r.get("nama") in OTHER_RELATIONS:
                kind, outgoing = OTHER_RELATIONS[r["nama"]]
            else:
                stats["jenis_tak_dikenal"] += 1
                continue
            target, target_id = target_key(r, slug_to_id, doc_keys)
            if not source or not target:
                stats["tak_terbaca"] += 1
                if len(unreadable) < 50:
                    unreadable.append(f"{d.get('nomor')} -> {r.get('nomor')}")
                continue
            src, dst, src_id, dst_id = (source, target, i, target_id) if outgoing else (target, source, target_id, i)
            if src == dst:
                self_refs.append(f"{d.get('nomor')}: {r.get('nama')} {r.get('nomor')}")
                continue
            k = claims.setdefault((src, kind, dst), Claim(src, kind, dst))
            k.dari_id, k.ke_id = k.dari_id or src_id, k.ke_id or dst_id
            side = "halaman_pengubah" if outgoing else "halaman_target"
            for items, value in ((k.dicatat_di, side), (k.nomor_mentah, r.get("nomor")),
                                 (k.tgl_mulai_berlaku, r.get("tgl_mulai_berlaku"))):
                if value and value not in items:
                    items.append(value)
    result = sorted(claims.values(), key=lambda k: (k.dari, k.jenis, k.ke))
    for k in result:
        k.ke_stub = k.ke_id is None
    report = {
        "baris_relasi": stats["baris"], "klaim_unik": len(result),
        "per_jenis": dict(Counter(k.jenis for k in result)),
        "dua_sisi": sum(not k.one_sided for k in result), "satu_sisi": sum(k.one_sided for k in result),
        "target_stub": sum(k.ke_stub for k in result),
        "tanggal_berlaku_berbeda_antar_sisi": sum(len(k.tgl_mulai_berlaku) > 1 for k in result),
        "tak_terbaca": stats["tak_terbaca"], "contoh_tak_terbaca": unreadable,
        "jenis_tak_dikenal": stats["jenis_tak_dikenal"], "diri_sendiri": self_refs,
    }
    return result, report
