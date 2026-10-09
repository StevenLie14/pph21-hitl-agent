from __future__ import annotations

import argparse
import collections
import concurrent.futures
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from taxagent.cli._common import llm_client  # noqa: E402
from taxagent.corpus.merge import listing_id  # noqa: E402
from taxagent.monitor.identity import canon_id  # noqa: E402
from taxagent.monitor.relation_llm import PROMPT_VERSION, extract_relations  # noqa: E402
from taxagent.paths import DATA  # noqa: E402

RELATION_DIR = DATA / "korpus_relasi"
MERGED_DIR = DATA / "korpus_gabung"


KIND_PHRASES = [
    ("peraturan pemerintah pengganti", "PERPPU"), ("keputusan presiden", "KEPPRES"), ("peraturan presiden", "PERPRES"),
    ("peraturan pemerintah", "PP"), ("undang-undang", "UU"), ("undang undang", "UU"),
    ("peraturan menteri keuangan", "PMK"), ("keputusan menteri keuangan", "KMK"),
    ("peraturan direktur jenderal", "PER-"), ("peraturan kepala", "PER-"), ("peraturan sekretaris", "PER-"),
    ("keputusan direktur jenderal", "KEP-"), ("keputusan kepala", "KEP-"), ("keputusan sekretaris", "KEP-"),
    ("peraturan menteri", None), ("keputusan menteri", None),
]
_RE_THIS_DOCUMENT = re.compile(r"(?:peraturan|keputusan|undang-undang)(?: [a-z-]+){0,3} ini\b")


def number_index(known: set[str]) -> dict[tuple[int, int], list[str]]:
    result: dict[tuple[int, int], list[str]] = collections.defaultdict(list)
    for k in known:
        n, t = re.search(r"\d+", k), re.search(r"(\d{4})$", k)
        if n and t:
            result[(int(n.group()), int(t.group(1)))].append(k)
    return result


def target_key(r, by_number: dict[tuple[int, int], list[str]] | None = None) -> str | None:
    if r.bukti and by_number is not None:
        clause = " ".join(r.bukti.klausa.split())
        m = re.search(rf"(?i)nomor\s*:?\s*(?:[A-Z]+[-.\s]*)?0*{r.nomor}\b", clause)
        before = _RE_THIS_DOCUMENT.sub(" ", clause[:m.start()].lower() if m else clause.lower())
        nearest = max(((before.rfind(f), len(f), prefix) for f, prefix in KIND_PHRASES if f in before), default=None,
                      key=lambda x: (x[0], x[1]))
        kind = nearest[2] if nearest else None
        if nearest and kind is None:
            return None
        candidates = [k for k in by_number.get((r.nomor, r.tahun), []) if kind and k.startswith(kind)]
        written = re.search(rf"\b0*{r.nomor}\s*/\s*([A-Z][A-Z0-9./\s]*?)\s*/\s*{r.tahun}", clause.upper())
        if written:
            segments = [re.sub(r"[^A-Z0-9]", "", s) for s in written.group(1).split("/")]
            if len(segments) > 1 and segments[0] in ("MK", "KMK"):
                segments = segments[1:]
            unit = "".join(segments)
            candidates = [k for k in candidates if k.count("/") != 2 or k.split("/")[1] == unit]
        folded = re.sub(r"[^A-Z0-9]", "", clause.upper())
        candidates = [k for k in candidates if k.count("/") != 2 or k.split("/")[1] in folded]
        if len(candidates) == 1:
            return candidates[0]
        if candidates:
            return None
    if r.ambigu:
        return None
    if r.jenis_peraturan in ("PER", "KEP", "SE"):
        if not r.penerbit:
            return None
        text = f"{r.jenis_peraturan}-{r.nomor}/{r.penerbit}/{r.tahun}"
    else:
        text = f"{r.jenis_peraturan} Nomor {r.nomor} Tahun {r.tahun}"
    ident = canon_id(text)
    return str(ident) if ident else None


def main() -> None:
    ap = argparse.ArgumentParser(description='Stage 4.3 remainder: relation sentences whose number the patterns could not read (``korpus_relasi/sisa_llm.jsonl``)')
    ap.add_argument("--max", dest="max", type=int, default=0, help="hanya N kalimat pertama (uji)")
    ap.add_argument("--before", dest="before", type=int, default=1500)
    ap.add_argument("--after", dest="after", type=int, default=1000)
    ap.add_argument("--parallel", dest="parallel", type=int, default=4)
    ap.add_argument("--provider")
    ap.add_argument("--model")
    a = ap.parse_args()

    remaining = [json.loads(b) for b in (RELATION_DIR / "sisa_llm.jsonl").read_text(encoding="utf-8").splitlines()
                 if b]
    if a.max:
        remaining = remaining[:a.max]
    index = [json.loads(b) for b in (MERGED_DIR / "indeks.jsonl").read_text(encoding="utf-8").splitlines() if b]
    by_id = {(e["sumber"], e["id"]): e for e in index}
    known = {e["kunci"] for e in index if e.get("kunci")}
    by_number = number_index(known)
    client, model_id = llm_client(a.provider, a.model, RELATION_DIR / "cache_llm.jsonl")
    if client is None:
        sys.exit(3)

    def one(s: dict) -> dict:
        e = by_id.get((s["sumber"], s["id"]))
        if not e or not e.get("teks"):
            return {"s": s, "galat": "dokumen tanpa teks di indeks", "relasi": [], "dibuang": [], "token": 0}
        text = Path(e["teks"]).read_text(encoding="utf-8")
        start = max(0, s["offset"][0] - a.before)
        window = text[start:s["offset"][1] + a.after]
        k = listing_id(e["jenis"], e["nomor"])
        h = extract_relations(window, client, (k.kind, k.number, k.year) if k else None)
        return {"s": s, "awal": start, "galat": h.galat, "relasi": h.relasi, "dibuang": h.dibuang, "token": h.token}

    counts = collections.Counter()
    findings: dict[tuple, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(a.parallel) as ex:
        for n, f in enumerate(concurrent.futures.as_completed([ex.submit(one, s) for s in remaining]), 1):
            try:
                h = f.result()
            except Exception as exc:  # noqa: BLE001
                counts["galat"] += 1
                print(f"[{n}/{len(remaining)}] GAGAL {type(exc).__name__}: {exc}", flush=True)
                continue
            s, counts["token"] = h["s"], counts["token"] + h["token"]
            counts["galat"] += bool(h["galat"])
            counts["dibuang_verifikasi"] += len(h["dibuang"])
            for r in h["relasi"]:
                dst = target_key(r, by_number)
                if dst is None:
                    counts["target_ambigu"] += 1
                    continue
                if dst not in known:
                    counts["target_di_luar_korpus"] += 1
                    continue
                if dst == s["dok"]:
                    continue
                b = r.bukti
                findings[(s["dok"], r.jenis, dst)] = {
                    "dari": s["dok"], "jenis": r.jenis, "ke": dst, "sumber": "teks_llm", "asal": "baru",
                    "dok_sumber": s["sumber"], "dari_id": s["id"], "kelas": "eksplisit",
                    "kutipan": b.klausa if b else r.kutipan, "pasal": b.pasal if b else None,
                    "bagian": b.bagian if b else None,
                    "offset": [h["awal"] + b.mulai, h["awal"] + b.akhir] if b else s["offset"],
                    "pasal_terdampak": r.pasal or None, "tgl_efektif": None, "tgl_efektif_sumber": "tidak_terekstrak",
                    "model": model_id, "prompt": PROMPT_VERSION}
            if n % 25 == 0 or n == len(remaining):
                print(f"[{n}/{len(remaining)}] relasi {len(findings)} | {dict(counts)}", flush=True)
    out = RELATION_DIR / ("temuan_llm_uji.jsonl" if a.max else "temuan_llm.jsonl")
    with open(out, "w", encoding="utf-8") as f:
        for t in findings.values():
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    report = {"kalimat": len(remaining), "relasi_disimpan": len(findings), "per_jenis": dict(collections.Counter(
        t["jenis"] for t in findings.values())), **counts, "model": model_id, "prompt": PROMPT_VERSION}
    (RELATION_DIR / ("laporan_llm_uji.json" if a.max else "laporan_llm.json")).write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
