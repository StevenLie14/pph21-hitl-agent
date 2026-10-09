from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from taxagent.corpus.relation_evidence import NormText, effective_date, evidence, parents_from_claims  # noqa: E402
from taxagent.paths import DATA  # noqa: E402

JDIH_DIR = DATA / "korpus_jdih"
PAJAK_DIR = DATA / "korpus_pajak"
MERGED_DIR = DATA / "korpus_gabung"
RELATION_DIR = DATA / "korpus_relasi"


def _jsonl(f: Path) -> list[dict]:
    return [json.loads(b) for b in f.read_text(encoding="utf-8").splitlines() if b.strip()]


def main() -> None:
    ap = argparse.ArgumentParser(description='Stage 4.2: verify the JDIH relation claims against the text of the amending regulation')
    ap.add_argument("--relations", dest="relations", type=Path, default=RELATION_DIR)
    a = ap.parse_args()

    claims = _jsonl(a.relations / "klaim.jsonl")
    parents = parents_from_claims(claims)
    counterpart = {x["id"]: x["pasangan"] for x in _jsonl(MERGED_DIR / "indeks.jsonl")
                   if x["sumber"] == "jdih" and x.get("pasangan")}
    quality = {x["kunci"]: x["status"] for x in _jsonl(JDIH_DIR / "mutu.jsonl")}
    pajak_quality = {x["kunci"]: x["status"] for x in _jsonl(PAJAK_DIR / "mutu.jsonl")}

    per_doc: dict[str | None, list[dict]] = defaultdict(list)
    for k in claims:
        per_doc[k["dari_id"]].append(k)
    result, classes = [], Counter()
    for i, doc_claims in per_doc.items():
        text = source = text_quality = None
        page = {}
        if i:
            f = JDIH_DIR / "halaman" / f"{i}.json"
            page = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
            if (JDIH_DIR / "teks" / f"{i}.txt").exists():
                text, source, text_quality = (JDIH_DIR / "teks" / f"{i}.txt").read_text(encoding="utf-8"), "jdih", \
                    quality.get(i, "belum_dinilai")
            elif counterpart.get(i) and (PAJAK_DIR / "teks" / f"{counterpart[i]}.txt").exists():
                text = (PAJAK_DIR / "teks" / f"{counterpart[i]}.txt").read_text(encoding="utf-8")
                source = f"pajak.go.id:{counterpart[i]}"
                text_quality = pajak_quality.get(counterpart[i], "belum_dinilai")
        if text is None:
            reason = "pengubah_stub" if not i else "teks_belum_ada"
            for k in doc_claims:
                result.append({**k, "kelas": "belum_bisa_dicek", "catatan": reason})
                classes["belum_bisa_dicek"] += 1
            continue
        t = NormText.from_raw(text)
        date, date_source = effective_date(t, page.get("tgl_pengundangan"), page.get("tgl_penetapan"))
        for k in doc_claims:
            b = evidence(t, k["ke"], k["jenis"], parents)
            classes[b["kelas"]] += 1
            result.append({**k, **b, "sumber_teks": source, "mutu_teks": text_quality,
                           "tgl_efektif": date, "tgl_efektif_sumber": date_source})
    result.sort(key=lambda r: (r["dari"], r["jenis"], r["ke"]))
    with open(a.relations / "verifikasi.jsonl", "w", encoding="utf-8") as f:
        for r in result:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    checked = [r for r in result if r["kelas"] != "belum_bisa_dicek"]
    report = {
        "klaim": len(result), "per_kelas": dict(classes),
        "kelas_per_jenis": {j: dict(Counter(r["kelas"] for r in result if r["jenis"] == j))
                            for j in sorted({r["jenis"] for r in result})},
        "tanpa_bukti_per_mutu": dict(Counter(r["mutu_teks"] for r in checked if r["kelas"] == "tanpa_bukti")),
        "bagian_bukti": dict(Counter(r.get("bagian") for r in checked if r["kelas"] in ("eksplisit", "tersirat"))),
        "tgl_efektif_sumber": dict(Counter(r["tgl_efektif_sumber"] for r in checked)),
        "tgl_efektif_beda_dengan_jdih": sum(1 for r in checked if r["tgl_efektif"] and r["tgl_mulai_berlaku"]
                                            and r["tgl_efektif"] not in r["tgl_mulai_berlaku"]),
    }
    (a.relations / "laporan_verifikasi.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                                         encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
