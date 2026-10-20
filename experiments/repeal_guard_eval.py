from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from taxagent.environment import load_env  # noqa: E402

OLD, NEW = "PMK 168 Tahun 2023", "PMK 12 Tahun 2025"
REPEAL_DATE = dt.date(2025, 7, 1)
BEFORE_REPEAL = {"q1", "q6"}
QUESTIONS = [
    ("q1", "Karyawan tetap status TK/0, gaji Rp15 juta sebulan, Maret 2025. Berapa PPh 21-nya?"),
    ("q2", "Saya pegawai tetap, menikah dengan 1 anak (K/1), gaji Rp20 juta per bulan. PPh 21 bulan Agustus 2025?"),
    ("q3", "Hitung PPh 21 setahun 2025 untuk pegawai tetap K/2 dengan gaji Rp12 juta per bulan, tanpa tunjangan lain."),
    ("q4", "Konsultan lepas (bukan pegawai) menerima honor Rp25 juta pada Oktober 2025, sudah punya NPWP. PPh 21-nya?"),
    ("q5", "Pegawai tetap TK/1 gaji Rp9 juta, bulan Desember 2025 (masa pajak terakhir, setahun penuh). Hitung PPh 21."),
    ("q6", "Pensiunan status K/0 menerima uang pensiun Rp6 juta per bulan pada Mei 2025. Berapa PPh 21?"),
]
_CLAIMS_IN_FORCE = re.compile(r"(?:pmk|peraturan menteri keuangan)\s*(?:nomor\s*)?168[^.\n]{0,80}"
                              r"(?<!tidak )(?<!sudah tidak )(?:masih berlaku|yang berlaku|berlaku saat ini)", re.I)
_SAYS_REPEALED = re.compile(r"(?:dicabut|tidak berlaku)", re.I)


def run(question: str, repealed: bool, log: Path):
    from taxagent.agent import runner as R
    from taxagent.monitor.memory_graph import from_texts
    from taxagent.tools import registry
    from taxagent.tools import regulation_graph as G

    docs = {OLD: {"teks": "Pasal 2 biaya jabatan ...", "mulai": "2024-01-01"},
            NEW: {"teks": f"Pasal 1 {OLD} dicabut dan dinyatakan tidak berlaku.", "mulai": "2025-07-01"}}
    rel = [{"dari": NEW, "jenis": "mencabut", "ke": OLD, "tgl_efektif": "2025-07-01"}] if repealed else []
    G.use_client(from_texts(docs, rel, [(OLD, "biaya_jabatan", ["2"]), (OLD, "ter_bulanan", ["3"])]))
    def status(result, kw):
        end = registry.period_end(result, kw)
        if repealed and end >= REPEAL_DATE:
            return [{"peraturan": OLD, "status": "dicabut", "pada": end.isoformat(), "oleh": [NEW]}]
        return [{"peraturan": OLD, "status": "berlaku", "pada": end.isoformat(), "oleh": []}]

    registry.result_basis_status = status
    import taxagent.taxes.pph21.tools as T
    T._basis_status = status
    try:
        return R.TaxAgent().ask(question)
    finally:
        G.use_client(None)


def score(turn, repealed: bool) -> dict:
    calcs = [j for j in turn.trace if j.name.startswith("calculate_")]
    auto = [j for j in turn.trace if j.name == "report_possibly_stale" and j.arguments.get("otomatis")]
    own = [j for j in turn.trace if j.name == "report_possibly_stale" and not j.arguments.get("otomatis")]
    answer = turn.answer or ""
    return {
        "hitung_berhasil": any(isinstance(j.result, dict) and j.result.get("berhasil") for j in calcs),
        "laporan_otomatis": len(auto),
        "laporan_model": len(own),
        "catatan_kode": "sudah tidak berlaku menurut graf" in answer,
        "jawaban_menyebut_dicabut": bool(_SAYS_REPEALED.search(answer)),
        "klaim_masih_berlaku": bool(_CLAIMS_IN_FORCE.search(answer)),
        "benar": (bool(calcs) and len(auto) == 1 and "sudah tidak berlaku menurut graf" in answer
                  and not _CLAIMS_IN_FORCE.search(answer)) if repealed
                 else (not auto and "sudah tidak berlaku menurut graf" not in answer),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    load_env()
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        import os

        os.environ["PPH21_PERMINTAAN_AGENT"] = str(Path(tmp) / "permintaan.jsonl")
        for repealed in (True, False):
            for qid, q in QUESTIONS:
                for i in range(1, args.runs + 1):
                    try:
                        turn = run(q, repealed, Path(tmp))
                        s = score(turn, repealed and qid not in BEFORE_REPEAL)
                        rec = {"id": qid, "dicabut": repealed, "sebelum_pencabutan": qid in BEFORE_REPEAL, "run": i, **s, "jawaban": turn.answer,
                               "tool": [j.name for j in turn.trace]}
                    except Exception as e:  # noqa: BLE001
                        rec = {"id": qid, "dicabut": repealed, "run": i, "benar": False, "error": repr(e)}
                    out.append(rec)
                    print(qid, "dicabut" if repealed else "kontrol", i, "benar" if rec["benar"] else "SALAH",
                          {k: rec.get(k) for k in ("laporan_otomatis", "laporan_model", "catatan_kode",
                                                   "klaim_masih_berlaku")}, flush=True)
    Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    groups = {"dicabut": lambda r: r["dicabut"] and r["id"] not in BEFORE_REPEAL,
              "dicabut, masa sebelum pencabutan": lambda r: r["dicabut"] and r["id"] in BEFORE_REPEAL,
              "kontrol": lambda r: not r["dicabut"]}
    for name, keep in groups.items():
        rs = [r for r in out if keep(r)]
        print(name, f"{sum(r['benar'] for r in rs)}/{len(rs)} benar")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
