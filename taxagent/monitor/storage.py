from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

VERSION = 2
SUPPORTED_VERSIONS = (1, 2)


@dataclass
class ImpactNote:
    id_dokumen: str
    identitas: str
    judul: str
    perihal: str
    tanggal_feed: str
    first_seen: str
    kategori: str
    alasan: list[str] = field(default_factory=list)
    key_terdampak: list[str] = field(default_factory=list)
    id_terkait: list[str] = field(default_factory=list)
    pemicu: list[str] = field(default_factory=list)
    sumber: str = "jdih_feed"
    pasal_terdampak: list[str] = field(default_factory=list)
    ditetapkan: str | None = None
    diundangkan: str | None = None
    mulai_berlaku_metadata: str | None = None
    mulai_berlaku_teks: str | None = None
    berlaku_untuk: list[str] = field(default_factory=list)
    retroaktif: bool = False
    dicabut_teks: list[dict] = field(default_factory=list)
    diubah_teks: list[str] = field(default_factory=list)
    relasi_portal: list[dict] = field(default_factory=list)
    selisih: list[str] = field(default_factory=list)
    galat_pengayaan: list[str] = field(default_factory=list)
    url_teks: str | None = None
    sumber_teks: str | None = None
    status_review: str = "baru"
    catatan_review: str = ""
    diterapkan_ke_yaml: bool = False
    pendapat_llm: dict | None = None
    dampak: dict | None = None


@dataclass
class MonitorState:
    dilihat: dict[str, dict] = field(default_factory=dict)
    catatan: list[ImpactNote] = field(default_factory=list)
    run_terakhir: str | None = None
    relasi_watchlist: dict[str, list[str]] = field(default_factory=dict)
    watchlist_terakhir: str | None = None
    bpk_dilihat: dict[str, str] = field(default_factory=dict)
    bpk_tertunda: dict[str, str] = field(default_factory=dict)
    bpk_terakhir: str | None = None
    dokumen_baru_terakhir: str | None = None
    kanari_sidik: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.dilihat

    def seen_ids(self) -> set[str]:
        return {v.get("identitas") for v in self.dilihat.values() if v.get("identitas")}


def load(path: Path) -> MonitorState:
    if not path.exists():
        return MonitorState()
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("versi") not in SUPPORTED_VERSIONS:
        raise ValueError(f"versi berkas status {data.get('versi')} tidak didukung (harus salah satu {SUPPORTED_VERSIONS})")
    notes = []
    for c in data.get("catatan", []):
        if c.get("berlaku_untuk") is None:
            c["berlaku_untuk"] = []
        elif isinstance(c["berlaku_untuk"], str):
            c["berlaku_untuk"] = [c["berlaku_untuk"]]
        notes.append(ImpactNote(**c))
    seen = data.get("dilihat", {})
    if data.get("versi") == 1:
        from .identity import from_slug

        for key, v in seen.items():
            ident = from_slug(key.rstrip("/").rsplit("/", 1)[-1])
            v.setdefault("identitas", str(ident) if ident else None)
    return MonitorState(
        dilihat=seen,
        catatan=notes,
        run_terakhir=data.get("run_terakhir"),
        relasi_watchlist=data.get("relasi_watchlist", {}),
        watchlist_terakhir=data.get("watchlist_terakhir"),
        bpk_dilihat=data.get("bpk_dilihat", {}),
        bpk_tertunda=data.get("bpk_tertunda", {}),
        bpk_terakhir=data.get("bpk_terakhir"),
        dokumen_baru_terakhir=data.get("dokumen_baru_terakhir"),
        kanari_sidik=data.get("kanari_sidik", []),
    )


def save(state: MonitorState, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(
            {
                "versi": VERSION,
                "run_terakhir": state.run_terakhir,
                "dokumen_baru_terakhir": state.dokumen_baru_terakhir,
                "watchlist_terakhir": state.watchlist_terakhir,
                "bpk_terakhir": state.bpk_terakhir,
                "dilihat": state.dilihat,
                "catatan": [asdict(c) for c in state.catatan],
                "relasi_watchlist": state.relasi_watchlist,
                "bpk_dilihat": state.bpk_dilihat,
                "bpk_tertunda": state.bpk_tertunda,
                "kanari_sidik": state.kanari_sidik,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    tmp.replace(path)
