from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from taxagent.corpus.relation_evidence import NormText, effective_date  # noqa: E402
from taxagent.corpus.relation_text import find_relations, pajak_status  # noqa: E402
from taxagent.paths import DATA  # noqa: E402

JDIH_DIR = DATA / "korpus_jdih"
PAJAK_DIR = DATA / "korpus_pajak"
MERGED_DIR = DATA / "korpus_gabung"
RELATION_DIR = DATA / "korpus_relasi"


def _jsonl(f: Path) -> list[dict]:
    return [json.loads(b) for b in f.read_text(encoding="utf-8").splitlines() if b.strip()]


def _write(f: Path, lines: list[dict]) -> None:
    with open(f, "w", encoding="utf-8") as h:
        for r in lines:
            h.write(json.dumps(r, ensure_ascii=False) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description='Stage 4.3: relations from the regulation text itself, including those JDIH does not record')
    ap.add_argument("--relations", dest="relations", type=Path, default=RELATION_DIR)
    a = ap.parse_args()

    index = _jsonl(MERGED_DIR / "indeks.jsonl")
    claims = {(k["dari"], k["jenis"], k["ke"]) for k in _jsonl(a.relations / "klaim.jsonl")}
    unevidenced = {(v["dari"], v["jenis"], v["ke"]) for v in _jsonl(a.relations / "verifikasi.jsonl")
                   if v["kelas"] == "tanpa_bukti"}
    details = {}
    for f in (PAJAK_DIR / "detail").glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        details[d.get("slug")] = d

    findings, remaining, counts, doc_dates = [], [], Counter(), []
    for x in index:
        if not x.get("kunci") or not x.get("teks") or not Path(x["teks"]).exists():
            continue
        counts[f"dok_berteks_{x['sumber']}"] += 1
        t = NormText.from_raw(Path(x["teks"]).read_text(encoding="utf-8"))
        if x["sumber"] == "jdih":
            f = JDIH_DIR / "halaman" / f"{x['id']}.json"
            page = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
            date, date_source = effective_date(t, page.get("tgl_pengundangan"), page.get("tgl_penetapan"))
        else:
            date, date_source = effective_date(t, None, (details.get(x["id"]) or {}).get("tanggal"))
        doc_dates.append({"kunci": x["kunci"], "sumber": x["sumber"], "tgl_efektif": date,
                          "tgl_efektif_sumber": date_source})
        relations, rest = find_relations(t, x["kunci"], x.get("jenis") or "")
        for r in relations:
            src, dst = (r["ke"], x["kunci"]) if r.pop("arah", None) == "masuk" else (x["kunci"], r["ke"])
            key = (src, r["jenis"], dst)
            origin = "konfirmasi_jdih" if key in claims else "baru"
            if key in unevidenced:
                origin = "naik_ke_eksplisit" if r["kelas"] == "eksplisit" else "konfirmasi_jdih"
            counts[f"{origin}:{r['kelas']}"] += 1
            findings.append({"dari": src, "jenis": r.pop("jenis"), "ke": dst, "sumber": "teks", "asal": origin,
                             "dok_sumber": x["sumber"], "dari_id": x["id"],
                             **{k: v for k, v in r.items() if k != "ke"},
                             "tgl_efektif": date, "tgl_efektif_sumber": date_source})
        for r in rest:
            remaining.append({"dok": x["kunci"], "sumber": x["sumber"], "id": x["id"], **r})
    revoked = {r["ke"] for r in findings if r["jenis"] == "mencabut" and r["kelas"] == "eksplisit"}
    revoked |= {v["ke"] for v in _jsonl(a.relations / "verifikasi.jsonl")
                if v["jenis"] == "mencabut" and v["kelas"] == "eksplisit"}
    pajak = [(x["kunci"], (details.get(x["id"]) or {}).get("status")) for x in index
             if x["sumber"] == "pajak" and x.get("kunci")]
    status = pajak_status(pajak, revoked)

    findings.sort(key=lambda r: (r["dari"], r["jenis"], r["ke"]))
    _write(a.relations / "temuan_teks.jsonl", findings)
    _write(a.relations / "status_pajak.jsonl", status)
    _write(a.relations / "sisa_llm.jsonl", remaining)
    _write(a.relations / "tanggal_dokumen.jsonl", doc_dates)
    report = {
        **dict(sorted(counts.items())),
        "relasi_baru_per_jenis": dict(Counter(r["jenis"] for r in findings if r["asal"] == "baru")),
        "relasi_baru_per_dok_sumber": dict(Counter(r["dok_sumber"] for r in findings if r["asal"] == "baru")),
        "status_pajak": dict(Counter((s["sumber"], s.get("konflik") is not None) for s in status).items()),
        "sisa_llm": len(remaining),
    }
    report["status_pajak"] = {f"{k[0]}{' (konflik)' if k[1] else ''}": v for k, v in report["status_pajak"].items()}
    (a.relations / "laporan_teks.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
