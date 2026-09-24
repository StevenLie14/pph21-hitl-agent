from __future__ import annotations

import datetime as dt
import json
import threading
from pathlib import Path

from ..settings import get_settings

REASONS = ("tabel_tarif_belum_ada", "peraturan_tidak_dikenal", "dasar_hukum_tidak_berlaku")
REPEAT_DAYS = 7
NOT_IN_FORCE = ("dicabut", "berakhir", "ditetapkan_menjadi")
_lock = threading.Lock()


def reports_file() -> Path:
    return get_settings().stale_reports_file


def _error(message: str, hint: str) -> dict:
    return {"berhasil": False, "galat": message, "saran": hint}


def _parse_date(text: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat((text or "")[:10])
    except ValueError:
        return None


def load(f: Path | None = None) -> list[dict]:
    f = f or reports_file()
    if not f.exists():
        return []
    records = []
    for line in f.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def open_reports(f: Path | None = None) -> list[dict]:
    by_number: dict[int, dict] = {}
    for r in load(f):
        if r.get("jenis") == "tandai":
            if r.get("nomor") in by_number:
                by_number[r["nomor"]]["selesai"] = r
        else:
            by_number[r["nomor"]] = {**r, "selesai": None}
    return [r for r in by_number.values() if r["selesai"] is None]


def _verify(reason: str, regulation: str, d: dt.date, graph, today: dt.date) -> tuple[str | None, dict | str]:
    if reason == "tabel_tarif_belum_ada":
        from ..taxes import get as tax_module

        years = tax_module().available_years()
        if d.year in years:
            return None, f"tabel tarif tahun {d.year} sudah ada"
        if d.year > today.year:
            return None, (f"tahun pajak {d.year} belum berjalan (hari ini {today.isoformat()}); bukan data usang. "
                          f"Bila memberi angka, sebut sebagai perkiraan memakai tabel tahun terbaru")
        if years and d.year < min(years):
            return None, f"tahun {d.year} sebelum tabel tertua ({min(years)}); bukan data usang, di luar cakupan"
        return f"tarif_{d.year}", {"tahun_tersedia": years}
    if not regulation.strip():
        return None, "isi argumen peraturan (jenis dan nomor, mis. 'PMK 168 Tahun 2023')"
    if graph is None:
        return regulation.strip(), {"graf": "tidak tersedia; klaim tidak bisa dicek"}
    h = graph(regulation=regulation, date=d.isoformat())
    if isinstance(h, dict) and str(h.get("galat", "")).startswith("graf tidak bisa diakses"):
        return regulation.strip(), {"graf": "tidak tersedia; klaim tidak bisa dicek"}
    found = isinstance(h, dict) and h.get("berhasil") and h.get("peraturan")
    if reason == "peraturan_tidak_dikenal":
        if found:
            return None, f"peraturan ada di graf ({h['peraturan'][0]['peraturan']}); pakai find_regulation"
        return regulation.strip(), {"graf": "tidak ditemukan"}
    if not found:
        return None, "peraturan tidak ada di graf; pakai alasan peraturan_tidak_dikenal"
    p = h["peraturan"][0]
    if p.get("status") not in NOT_IN_FORCE:
        return None, f"{p['peraturan']} berstatus {p.get('status')} pada {d.isoformat()} menurut graf"
    return p["peraturan"], {"status": p.get("status"), "oleh": p.get("oleh"), "sejak": p.get("sejak")}


def report(alasan: str, keterangan: str, peraturan: str = "", tanggal_fakta: str = "",
           graf=None, f: Path | None = None, hari_ini: dt.date | None = None) -> dict:
    if alasan not in REASONS:
        return _error(f"alasan '{alasan}' tidak dikenal", f"Pilih salah satu: {', '.join(REASONS)}.")
    if not (keterangan or "").strip():
        return _error("keterangan kosong", "Tulis singkat apa yang membuatmu menduga data usang.")
    today = hari_ini or dt.date.today()
    if alasan == "tabel_tarif_belum_ada" and _parse_date(tanggal_fakta) is None:
        return _error("tanggal_fakta kosong atau bukan YYYY-MM-DD",
                      "Isi tanggal_fakta dengan tanggal/masa pajak yang ditanyakan pengguna (mis. '2027-01-31'), "
                      "lalu panggil ulang.")
    d = _parse_date(tanggal_fakta) or today
    subject, evidence = _verify(alasan, peraturan or "", d, graf, today)
    if subject is None:
        return _error(f"klaim tidak terbukti: {evidence}",
                      "Jangan laporkan ini; lanjutkan menjawab dengan data yang ada.")
    f = f or reports_file()
    with _lock:
        records = load(f)
        since = (today - dt.timedelta(days=REPEAT_DAYS)).isoformat()
        for r in open_reports(f):
            if r["alasan"] == alasan and r["objek"] == subject and r["tanggal"] >= since:
                return {"berhasil": True, "dicatat": False, "nomor": r["nomor"],
                        "pesan": f"sudah dilaporkan pada {r['tanggal']} (nomor {r['nomor']}), menunggu pemeriksaan"}
        number = 1 + max((r.get("nomor", 0) for r in records if r.get("jenis") != "tandai"), default=0)
        record = {"jenis": "permintaan", "nomor": number, "tanggal": today.isoformat(), "alasan": alasan,
                  "objek": subject, "peraturan": peraturan, "tanggal_fakta": d.isoformat(),
                  "keterangan": keterangan.strip()[:500], "bukti": evidence}
        f.parent.mkdir(parents=True, exist_ok=True)
        with f.open("a", encoding="utf-8") as out:
            out.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    return {"berhasil": True, "dicatat": True, "nomor": number,
            "pesan": "permintaan pemeriksaan dicatat untuk pemantau; data yang dipakai jawaban ini belum berubah"}


def resolve(nomor: int, hasil: str, catatan: str = "", f: Path | None = None) -> dict:
    f = f or reports_file()
    if not any(r["nomor"] == nomor for r in open_reports(f)):
        raise ValueError(f"permintaan nomor {nomor} tidak ada atau sudah ditandai")
    record = {"jenis": "tandai", "nomor": nomor, "tanggal": dt.date.today().isoformat(), "hasil": hasil,
              "catatan": catatan}
    with _lock, f.open("a", encoding="utf-8") as out:
        out.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def monitor_warnings(f: Path | None = None) -> list[str]:
    return [f"permintaan agent #{r['nomor']} ({r['tanggal']}): {r['alasan']} {r['objek']}: {r['keterangan'][:160]}"
            for r in open_reports(f)]
