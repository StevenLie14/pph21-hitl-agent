from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from taxagent.corpus.chunking import chunk, search_text  # noqa: E402
from taxagent.corpus.full_graph import clear, edge_from, merge_relations, plan, update, write  # noqa: E402
from taxagent.corpus.pages import page_starts  # noqa: E402
from taxagent.corpus.status import Edge, check_integrity, compute  # noqa: E402
from taxagent.corpus.word_split import Lexicon, split_text  # noqa: E402
from taxagent.monitor.classify import load_watchlist  # noqa: E402
from taxagent.paths import DATA  # noqa: E402
from taxagent.taxes.pph21.calc.rates import DATA_DIR  # noqa: E402

JDIH_DIR = DATA / "korpus_jdih"
PAJAK_DIR = DATA / "korpus_pajak"
MERGED_DIR = DATA / "korpus_gabung"
RELATION_DIR = DATA / "korpus_relasi"
GRAPH_DIR = DATA / "korpus_graf"
_RE_TAX = re.compile(r"pajak|perpajakan|\bpph\b|\bppn\b|penghasilan|bea meterai|fiskal|ditanggung pemerintah", re.I)


def _jsonl(f: Path) -> list[dict]:
    return [json.loads(b) for b in f.read_text(encoding="utf-8").splitlines() if b.strip()] if f.exists() else []


def _json(f: Path) -> dict:
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _fingerprint(f: Path) -> str:
    return hashlib.sha1(f.read_bytes()).hexdigest()[:12] if f.exists() else "-"


def documents(index: list[dict], text_dates: dict[str, dict], details: dict[str, dict]) -> tuple[list[dict], Counter]:
    counts = Counter()
    until = {str(e.identity): e.valid_until for e in load_watchlist().regulations if e.valid_until}
    chosen: dict[str, dict] = {}
    for x in index:
        if not x.get("kunci"):
            counts["tanpa_kunci"] += 1
            continue
        has_text = bool(x.get("teks") and Path(x["teks"]).exists())
        rank = (has_text, x["sumber"] == "jdih")
        if x["kunci"] not in chosen or rank > chosen[x["kunci"]]["_rank"]:
            chosen[x["kunci"]] = {**x, "_rank": rank, "_has_text": has_text}
    result = []
    for k, x in chosen.items():
        d = {"kunci": k, "jenis_dok": x.get("jenis"), "nomor_asli": x.get("nomor"),
             "judul": x.get("judul_teks") or x.get("judul"), "tahun": x.get("tahun"), "sumber_dok": x["sumber"],
             "mutu": x.get("mutu"), "punya_teks": x["_has_text"], "berlaku_sampai": until.get(k)}
        if x.get("judul_teks"):
            d["judul_listing"] = x.get("judul")
        if x["sumber"] == "jdih":
            page = _json(JDIH_DIR / "halaman" / f"{x['id']}.json")
            record = _json(JDIH_DIR / "berkas" / f"{x['id']}.json")
            d.update({"id_jdih": x["id"], "url": page.get("url"), "url_berkas": record.get("url"),
                      "jenis_berkas": record.get("jenis"), "tgl_penetapan": page.get("tgl_penetapan"),
                      "tgl_pengundangan": page.get("tgl_pengundangan"), "tgl_mulai_jdih": page.get("tgl_mulai_berlaku"),
                      "tgl_selesai_jdih": page.get("tgl_selesai_berlaku"), "riwayat_jdih": page.get("riwayat_terakhir")})
            if x.get("pasangan"):
                d["label_pajak_pasangan"] = (details.get(x["pasangan"]) or {}).get("status")
        else:
            det = details.get(x["id"]) or {}
            d.update({"slug_pajak": x["id"], "url": det.get("url"), "tgl_penetapan": det.get("tanggal"),
                      "label_pajak": det.get("status")})
        t = text_dates.get(k) or {}
        if t.get("tgl_efektif"):
            d["mulai"], d["mulai_sumber"] = t["tgl_efektif"], f"teks:{t.get('tgl_efektif_sumber')}"
        elif d.get("tgl_mulai_jdih"):
            d["mulai"], d["mulai_sumber"] = d["tgl_mulai_jdih"], "jdih"
        elif d.get("tgl_pengundangan") or d.get("tgl_penetapan"):
            d["mulai"] = d.get("tgl_pengundangan") or d.get("tgl_penetapan")
            d["mulai_sumber"] = "perkiraan:pengundangan_atau_penetapan"
        d["_text"] = x.get("teks") if x["_has_text"] else None
        d["_tax"] = x["sumber"] == "pajak" or bool(_RE_TAX.search(x.get("judul") or ""))
        result.append(d)
    return result, counts


def chunks(docs: list[dict], lexicon: Lexicon | None) -> list[dict]:
    result = []
    for d in docs:
        if not (d["_tax"] and d["_text"]):
            continue
        text = Path(d["_text"]).read_text(encoding="utf-8")
        starts = page_starts(JDIH_DIR, d["id_jdih"], text) if d.get("id_jdih") else None
        name = d["kunci"]
        for p in chunk(text):
            page = sum(1 for a in starts if a <= p.start) if starts else None
            result.append({"id": f"{name}#{p.order}", "peraturan": name, "urutan": p.order, "label_pasal": p.label,
                           "teks": p.text, "offset_awal": p.start, "offset_akhir": p.end, "halaman": page,
                           "teks_cari": search_text(name, d.get("judul") or "", p.label, p.text,
                                                    (lambda s: split_text(s, lexicon)[0]) if lexicon else None)})
    return result


def compare_status(r, claims: list[dict], today: dt.date) -> list[dict]:
    incoming = defaultdict(list)
    for k in claims:
        date = (k.get("tgl_mulai_berlaku") or [None])[0]
        incoming[k["ke"]].append(Edge(k["dari"], k["jenis"], k["ke"], "eksplisit", date))
    outgoing = defaultdict(list)
    for k in claims:
        outgoing[k["dari"]].append(Edge(k["dari"], k["jenis"], k["ke"], "eksplisit", None))
    result = []
    for key, p in r.regulations.items():
        naive = compute(key, today, incoming[key], outgoing[key]).status
        label = p.get("label_pajak") or p.get("label_pajak_pasangan")
        result.append({"kunci": key, "graf": p["status_hari_ini"], "graf_pasti": p["status_pasti"],
                       "jdih_naif": naive, "label_pajak": label, "riwayat_jdih": p.get("riwayat_jdih"),
                       "stub": p["stub"]})
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description='Stage 5: build the full regulation graph from the Stage 2-4 outputs and load it into the ``neo4j-v2`` instance.')
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", dest="dry_run", action="store_true")
    g.add_argument("--write", dest="write", action="store_true", help="kosongkan neo4j-v2 lalu muat")
    g.add_argument("--update", dest="update", action="store_true",
                   help="tanpa mengosongkan: perbarui properti peraturan dan relasi status (potongan, vektor, FAQ, "
                        "dasar hukum tetap)")
    a = ap.parse_args()
    today = dt.date.today()
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)

    index = _jsonl(MERGED_DIR / "indeks.jsonl")
    details = {d.get("slug"): d for d in (_json(f) for f in (PAJAK_DIR / "detail").glob("*.json"))}
    text_dates = {x["kunci"]: x for x in _jsonl(RELATION_DIR / "tanggal_dokumen.jsonl")}
    docs, counts = documents(index, text_dates, details)
    doc_dates = {d["kunci"]: d.get("tgl_pengundangan") or d.get("tgl_penetapan") for d in docs}
    verified, findings = _jsonl(RELATION_DIR / "verifikasi.jsonl"), _jsonl(RELATION_DIR / "temuan_teks.jsonl")
    llm_file = RELATION_DIR / "temuan_llm.jsonl"
    if llm_file.exists():
        seen = {(x["dari"], x["jenis"], x["ke"]) for x in findings}
        findings += [t for t in _jsonl(llm_file) if (t["dari"], t["jenis"], t["ke"]) not in seen]
    claim_file = RELATION_DIR / "temuan_llm_klaim.jsonl"
    if claim_file.exists():
        seen = {(x["dari"], x["jenis"], x["ke"]) for x in findings}
        findings += [t for t in _jsonl(claim_file) if (t["dari"], t["jenis"], t["ke"]) not in seen]
    relations = merge_relations(verified, findings, doc_dates)
    lexicon_file = JDIH_DIR / "kamus_pecah.json"
    chunk_rows = chunks(docs, Lexicon.load(lexicon_file) if lexicon_file.exists() else None)
    impact_graph = yaml.safe_load((DATA_DIR / "graf_dampak.yaml").read_text(encoding="utf-8"))
    definitions = []
    for e in load_watchlist().regulations:
        if e.role != "dasar":
            continue
        per_key: dict[str, list[str]] = {}
        for article, keys in e.governed_articles:
            for key in keys:
                per_key.setdefault(key, []).append(article)
        definitions += [(str(e.identity), key, per_key.get(key, [])) for key in set(e.governs) | set(per_key)]
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    meta = {"tanggal": today.isoformat(), "commit": commit, "skema": "graf_penuh-1",
            **{f"sidik_{f.stem}": _fingerprint(f) for f in (MERGED_DIR / "indeks.jsonl",
                                                            RELATION_DIR / "verifikasi.jsonl",
                                                            RELATION_DIR / "temuan_teks.jsonl")}}
    legal_basis = [x for x in _jsonl(RELATION_DIR / "dasar_hukum.jsonl") if x["dari"] in {d["kunci"] for d in docs}]
    r = plan([{k: v for k, v in d.items() if not k.startswith("_")} for d in docs], relations, chunk_rows,
             impact_graph["parameter"], definitions, meta, today, legal_basis)

    integrity = check_integrity([edge_from(x) for x in relations.values()],
                                {k: p.get("tahun") for k, p in r.regulations.items() if p.get("tahun")},
                                {k: p["mulai"] for k, p in r.regulations.items() if p.get("mulai")})
    comparison = compare_status(r, _jsonl(RELATION_DIR / "klaim.jsonl"), today)
    for name, rows in (("integritas", integrity), ("banding_status", comparison)):
        with open(GRAPH_DIR / f"{name}.jsonl", "w", encoding="utf-8") as f:
            for x in rows:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
    non_stub = [b for b in comparison if not b["stub"]]
    report = {
        "tanggal": today.isoformat(), "peraturan": len(r.regulations),
        "stub": sum(p["stub"] for p in r.regulations.values()),
        "indeks_tanpa_kunci": counts["tanpa_kunci"], "relasi": len(relations),
        "relasi_per_jenis_bukti": dict(Counter(f"{x['jenis']}:{x['bukti']}" for x in relations.values())),
        "relasi_per_sumber": dict(Counter(x["sumber"] for x in relations.values())),
        "potongan": len(chunk_rows), "dok_berpotongan": len({p["peraturan"] for p in chunk_rows}),
        "potongan_berhalaman": sum(1 for p in chunk_rows if p["halaman"]),
        "status_hari_ini": dict(Counter(p["status_hari_ini"] for p in r.regulations.values() if not p["stub"])),
        "status_tidak_pasti": sum(1 for p in r.regulations.values() if not p["stub"] and not p["status_pasti"]),
        "mulai_sumber": dict(Counter((p.get("mulai_sumber") or "tidak_ada").split(":")[0]
                                     for p in r.regulations.values() if not p["stub"])),
        "integritas": dict(Counter(x["jenis"] for x in integrity)),
        "graf_vs_jdih_naif_beda": sum(1 for b in non_stub if b["graf"] != b["jdih_naif"]),
        "graf_vs_jdih_naif": dict(Counter(f"{b['jdih_naif']}->{b['graf']}" for b in non_stub
                                          if b["graf"] != b["jdih_naif"]).most_common(12)),
        "graf_vs_label_pajak": dict(Counter(f"{b['label_pajak']}|{b['graf']}" for b in non_stub
                                            if b["label_pajak"]).most_common(12)),
        "parameter": len(r.parameters), "mendefinisikan": len(r.defines), "berdasarkan": len(r.basis),
        "bangun": meta,
    }
    (GRAPH_DIR / "laporan.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    if not (a.write or a.update):
        return
    from taxagent.environment import load_neo4j_env
    from taxagent.monitor.graph_v2 import Neo4jV2Client

    load_neo4j_env()
    neo = Neo4jV2Client()
    try:
        if a.update:
            print("diperbarui:", json.dumps(update(neo, r, report=lambda s: print(s, flush=True)), ensure_ascii=False))
            return
        print("mengosongkan neo4j-v2 (graf pilot sudah diarsipkan)", flush=True)
        clear(neo)
        print("ditulis:", json.dumps(write(neo, r, report=lambda s: print(s, flush=True)), ensure_ascii=False))
    finally:
        neo.close()


if __name__ == "__main__":
    main()
