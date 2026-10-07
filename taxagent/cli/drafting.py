from __future__ import annotations

import json
import re
from pathlib import Path

from ..environment import load_neo4j_env
from ._common import EXIT_FAILED, error, llm_client, write_report


def _read_source(s: str, ocr: bool = False) -> tuple[str, bytes | None]:
    url = re.match(r"https?://", s) is not None
    if s.lower().endswith(".txt") and not url:
        return Path(s).read_text(encoding="utf-8"), None
    from ..monitor.enrichment import text_from_file

    if url:
        from ..monitor.sources import fetch

        content = fetch(s)
    else:
        content = Path(s).read_bytes()
    if ocr:
        from ..monitor.ocr import ocr_if_scanned

        h = ocr_if_scanned(content)
        if h.text is not None:
            print(f"PDF scan: teks dari OCR ulang PaddleOCR ({'cache' if h.source == 'ocr_cache' else 'baru'})")
            return h.text, content
        if h.pdf_kind == "scan":
            error(f"PERINGATAN: PDF scan tetapi OCR ulang gagal ({h.error}); memakai lapisan teks PDF "
                  "(salah baca lebih banyak, draf lebih sering ditahan G3)")
    return text_from_file(content, s), content


def _ter_table(content: bytes, name: str, args):
    from ..update.ter_table import read_table, vision_client

    h = read_table(content, name, vision_client(args.provider, args.model, args.cache) if args.llm else None)
    for line in h.lines:
        (error if line.startswith("PERINGATAN") else print)(line)
    return None if h.extraction is None else (h.extraction, h.llm)


def _source_name(s: str) -> str:
    return s if s.startswith("http") else Path(s).name


def _phase1_note(args):
    from ..monitor import load

    status = load(Path(args.status))
    if not 1 <= args.note <= len(status.catatan):
        error(f"nomor catatan {args.note} di luar 1..{len(status.catatan)} ({args.status})")
        return EXIT_FAILED
    c = status.catatan[args.note - 1]
    print(f"Catatan {args.note}: [{c.kategori}] {c.identitas} {c.judul[:80]}")
    if c.kategori != "dasar":
        print(f"kategori {c.kategori}: bukan perubahan angka, tidak ada draf tarif (Fase 2 hanya untuk kategori dasar)")
        return 0
    if not c.url_teks:
        error("catatan tidak menyimpan URL teks peraturan; beri --source")
        return EXIT_FAILED
    return c


def _merge_llm(merged, new, conflicts: set):
    if merged is None:
        return new
    for key, v in new.values.items():
        if key in conflicts:
            continue
        if key in merged.values and merged.values[key] != v:
            merged.dropped.append(f"{key}: sumber berbeda ({merged.values[key]} dan {v})")
            merged.values.pop(key)
            conflicts.add(key)
        else:
            merged.values.setdefault(key, v)
    merged.valid &= new.valid
    merged.dropped += new.dropped
    return merged


def _g8_status(c) -> dict | None:
    from ..monitor.identity import canon_id
    from ..update.source_status import status_from_graph

    ident = canon_id(c.identitas or "")
    try:
        load_neo4j_env()
        st = status_from_graph(str(ident)) if ident else None
    except Exception as e:  # noqa: BLE001
        error(f"graf peraturan tidak bisa ditanya ({type(e).__name__}); G8 tidak dijalankan")
        return None
    return {_source_name(c.url_teks): st} if st is not None else {}


def cmd_draft_rates(args) -> int:
    from ..update import DraftRejected, assemble_draft, extract_amounts, write_draft
    from ..update.gates import GateContext, effective_from_text, effective_year

    sources, keys, note = list(args.source or []), None, None
    if args.note is not None:
        note = _phase1_note(args)
        if isinstance(note, int):
            return note
        sources.append(note.url_teks)
        keys = sorted(set(note.key_terdampak) | set((note.dampak or {}).get("keys", [])))
    if not sources:
        error("beri --source atau --note")
        return EXIT_FAILED
    if args.keys:
        keys = [k.strip() for k in args.keys.split(",") if k.strip()]
    context = GateContext(phase1_keys=keys)

    client = None
    if args.llm:
        client, _ = llm_client(args.provider, args.model, args.cache)
        if client is None:
            return EXIT_FAILED

    results, llm, conflicts = [], None, set()
    for s in sources:
        try:
            text, content = _read_source(s, ocr=not args.no_ocr)
        except Exception as e:  # noqa: BLE001
            error(f"GAGAL membaca sumber {s}: {type(e).__name__}: {e}")
            return EXIT_FAILED
        name = _source_name(s)
        if content is not None and content[:5] == b"%PDF-" and not args.no_table and not args.no_ocr:
            from ..monitor.text_quality import pdf_kind
            from ..update.body_tables import reflow

            r = reflow(text, content) if pdf_kind(content) == "scan" else None
        else:
            r = None
        if r is not None:
            text = r.text
            for line in r.lines:
                (error if line.startswith("PERINGATAN") else print)(line)
        results.append(extract_amounts(text, name))
        context.in_force[name] = effective_from_text(text, name)
        if client is not None:
            from ..update.llm import extract_llm

            llm = _merge_llm(llm, extract_llm(text, client), conflicts)
        from ..update.ter_table import has_ter_table

        if content is not None and content[:5] == b"%PDF-" and not args.no_table and has_ter_table(text):
            table = _ter_table(content, name, args)
            if table is not None:
                results.append(table[0])
                if table[1] is not None:
                    llm = _merge_llm(llm, table[1], conflicts)
    context.llm = llm
    if note is not None:
        context.source_status = _g8_status(note)

    year = args.year
    if year is None:
        text_years = {effective_year(b)[0] for b in context.in_force.values()} - {None}
        if len(text_years) != 1:
            error("tahun pajak tidak bisa ditentukan dari teks (tengah tahun, tidak terbaca, atau berbeda antar-sumber); "
                  "beri --year")
            return EXIT_FAILED
        year = text_years.pop()
        print(f"Tahun pajak dari teks: {year}")

    try:
        d = assemble_draft(year, results, args.base_year, context)
        written = write_draft(d, Path(args.output))
        if d.berubah:
            from ..update.review import save_json

            written.append(save_json(d, Path(args.output), {
                "identitas": note.identitas if note else None, "url_teks": note.url_teks if note else None,
                "sumber": sources}))
    except (DraftRejected, ValueError, FileExistsError) as e:
        error(f"DITOLAK: {e}")
        return EXIT_FAILED
    for p in d.comparisons:
        print(f"{p.key:28} {p.status}")
    for x in d.mismatches:
        print(f"tidak dipakai (digit != terbilang): {x}")
    if d.decision != "tidak_ada_perubahan":
        print(f"Gerbang: {d.decision}")
        for a in d.decision_reason:
            print(f"  - {a}")
    print("Ditulis: " + ", ".join(str(p) for p in written))
    if d.berubah:
        print(f"Review manusia: pph21 review-draft --draft {Path(args.output) / f'draf_tarif_{d.year}.json'}")
    return 1 if d.berubah or d.decision == "tahan" else 0


def cmd_review_draft(args) -> int:
    from ..update.review import apply_decisions, cards, draft_fingerprint, embed_data, render_page, write_patch

    draft_file = Path(args.draft)
    draft = json.loads(draft_file.read_text(encoding="utf-8"))
    year, folder = draft["tahun"], Path(args.output) if args.output else draft_file.parent
    key_file = folder / f"review_kunci_{year}.json"
    if args.decision is None:
        card_list = cards(draft)
        if not card_list:
            print("Draf tidak berisi key yang berubah; tidak ada yang perlu direview.")
            return 0
        answer_key = []
        if args.insert:
            card_list, answer_key = embed_data(card_list, args.insert, args.seed)
        folder.mkdir(parents=True, exist_ok=True)
        html_file = folder / f"review_tarif_{year}.html"
        html_file.write_text(render_page(draft, card_list), encoding="utf-8")
        key_file.write_text(json.dumps({"sidik": draft_fingerprint(draft), "kartu": card_list, "sisipan": answer_key},
                                       ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(f"Halaman review: {html_file.resolve()}")
        print(f"{len(card_list)} kartu" + (f" (termasuk {len(answer_key)} sisipan; kunci di {key_file.name})" if answer_key else ""))
        print(f"Setelah ekspor: pph21 review-draft --draft {draft_file} --decision keputusan_review_{year}.json")
        return 0
    decisions = json.loads(Path(args.decision).read_text(encoding="utf-8"))
    if not key_file.exists():
        error(f"{key_file} tidak ada; buat halaman review dulu")
        return EXIT_FAILED
    key_data = json.loads(key_file.read_text(encoding="utf-8"))
    if decisions.get("tahun") != year or decisions.get("sidik_draf") != key_data["sidik"] or key_data["sidik"] != draft_fingerprint(draft):
        error("keputusan bukan untuk draf ini (tahun atau sidik draf berbeda); buat ulang halaman review")
        return EXIT_FAILED
    patch, log, summary = apply_decisions(draft, key_data["kartu"], decisions, key_data["sisipan"])
    try:
        written = write_patch(draft, patch, log, summary, decisions.get("reviewer") or "-", folder)
    except (ValueError, FileExistsError) as e:
        error(f"DITOLAK: {e}")
        return EXIT_FAILED
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print("Ditulis: " + ", ".join(str(p) for p in written))
    return 0


def _evaluation_client(args):
    meta = {"model": "-", "prompt": "-"}
    if not args.llm:
        return None, meta
    from ..update.llm import PROMPT_VERSION

    client, model_id = llm_client(args.provider, args.model, args.cache)
    if client is None:
        return None, None
    meta = {"model": model_id, "prompt": PROMPT_VERSION}
    if args.pair == "pola+llm":
        return client, meta
    from ..update.evaluation import Pair

    client2 = None
    if args.pair == "graf+llm":
        client2, meta["model2"] = llm_client(args.provider, args.second_model, args.cache)
        if client2 is None:
            return None, None
    return Pair(args.pair, client, client2), meta


def _g8_status_dataset(labels: dict, current: bool) -> dict:
    from ..monitor.identity import document_ids
    from ..update.source_status import status_from_graph

    load_neo4j_env()
    status = {}
    for d, info in labels.items():
        ident = document_ids(d, info.get("nomor"))
        status[d] = status_from_graph(str(ident), None if current else ident.year) if ident else None
    return status


def cmd_draft_evaluate(args) -> int:
    from ..update.evaluation import evaluate, load_labels, markdown_report, texts_from_dataset

    labels = load_labels()
    from ..corpus.text_source import jdih_first

    texts, sources = jdih_first(list(labels), texts_from_dataset(labels, Path(args.text_dataset)))
    missing = [i for i in labels if i not in texts]
    if missing:
        error(f"teks tidak ditemukan di korpus maupun dataset: {', '.join(missing)}")
    client, meta = _evaluation_client(args)
    if meta is None:
        return EXIT_FAILED
    meta["sumber_teks"] = sources
    status = None
    if not args.no_graph:
        try:
            status = _g8_status_dataset(labels, args.g8_now)
        except Exception as e:  # noqa: BLE001
            error(f"graf peraturan tidak bisa ditanya ({type(e).__name__}: {e}); pakai --no-graph untuk menjalankan "
                  "tanpa G8 (semua draf berubah ditahan)")
            return EXIT_FAILED
        meta["g8"] = {d: s for d, s in status.items() if s}
    tables = None
    if args.lampiran_tables:
        from ..corpus.text_source import CorpusIndex
        from ..update.backtest import pdf_table_reader
        from ..update.body_tables import reflow_source
        from ..update.ter_table import has_ter_table, vision_client

        corpus = CorpusIndex()
        rebuilt = []
        for i, t in list(texts.items()):
            src = corpus.pick(i)
            if src is not None and src.text == t:
                r = reflow_source(src)
                texts[i] = r.text
                rebuilt += [i] * bool(r.pages)
                for line in r.lines:
                    error(f"  {i}: {line}")
        meta["tabel_pasal"] = f"OCR kotak, disusun ulang per baris: {', '.join(rebuilt) or '-'}"

        reader = pdf_table_reader(vision_client(args.provider, args.model, args.vision_cache) if args.llm else None,
                                  progress=lambda line: error(f"  {line}"))
        tables = {}
        for i, t in texts.items():
            src = corpus.pick(i)
            if src is not None and has_ter_table(t) and (r := reader(src, t)) is not None:
                tables[i] = r
        meta["tabel_lampiran"] = "PDF JDIH lokal: OCR kotak" + (" + LLM vision" if args.llm else "")
    h = evaluate(labels, texts, client, mutations=not args.no_mutation, workers=args.parallel,
                 progress=lambda n, i: error(f"  [{n}/{len(texts)}] {i}"), status=status, tables=tables)
    md = markdown_report(h, meta)
    suffix = ("" if args.pair == "pola+llm" else "_" + args.pair.replace("+", "_")) \
        + ("_g8_sekarang" if args.g8_now else "")
    write_report(args.output, f"draf_evaluasi{suffix}", md, {"meta": meta, **h})
    print(md)
    return 1 if any(k["salah_lolos"] for k in h["mutasi"]) else 0


def cmd_draft_backtest(args) -> int:
    from ..monitor.identity import document_ids
    from ..update.backtest import backtest, markdown_report
    from ..update.source_status import status_from_graph

    client, meta = _evaluation_client(args)
    if meta is None:
        return EXIT_FAILED
    status_for = None
    if not args.no_graph:
        load_neo4j_env()

        def status_for(name: str, number: str, year: int):
            ident = document_ids(name, number)
            return status_from_graph(str(ident), year) if ident else None

    classifier = None
    if args.llm:
        from ..monitor.classify_llm import LLMCache, LLMClassifier, langchain_call

        call, model_id = langchain_call(args.provider, args.model)
        classifier = LLMClassifier.with_keyword_text(call, model_id, LLMCache(Path(args.monitor_cache)))
    phase1_for = None
    if args.phase1_llm:
        from ..monitor.classify import load_watchlist
        from ..monitor.evaluation import without_self
        from ..monitor.identity import canon_id
        from ..monitor.impact import build_graph, union_impact
        from ._common import llm_client

        impact_client, _ = llm_client(args.provider, args.model, args.impact_cache)
        if impact_client is None:
            return EXIT_FAILED
        wl = load_watchlist()
        impact_graph = build_graph(wl)

        def phase1_for(name: str, number: str, title: str, text: str) -> list[str]:
            ident = canon_id(number) or canon_id(name)
            r = union_impact(title, "", ident, text, without_self(wl, ident), impact_client,
                             impact_graph.without(ident))
            return sorted(r.keys)
    read_table = None
    if args.lampiran_tables:
        from ..update.backtest import pdf_table_reader
        from ..update.ter_table import vision_client

        read_table = pdf_table_reader(vision_client(args.provider, args.model, args.vision_cache) if args.llm else None,
                                      progress=lambda line: error(f"  {line}"))
        meta["tabel_lampiran"] = "PDF JDIH lokal: OCR kotak" + (" + LLM vision" if args.llm else "")
        meta["tabel_pasal"] = "tabel lapisan di pasal disusun ulang per baris dari OCR kotak (PDF JDIH lokal)"
    if args.cumulative:
        from ..update.backtest import cumulative, cumulative_report

        h = cumulative(Path(args.text_dataset), client, status_for, progress=lambda n, t, d: error(f"  [{n}/{t}] {d}"),
                       classifier=classifier, phase1_for=phase1_for, read_table=read_table,
                       body_tables=args.lampiran_tables, note=lambda line: error(f"  {line}"))
        md = cumulative_report(h, meta)
        name = "draf_kumulatif" + ("_umpan_ke_jawaban" if args.phase1_llm else "") + ("" if args.llm else "_tanpa_llm")
        write_report(args.output, name, md, {"meta": meta, **h})
        print(md)
        return 1 if any(r["salah_lolos"] for r in h["run"]) else 0
    variants = ("asli",) if args.no_mutation else ("asli", "ubah")
    h = backtest(Path(args.text_dataset), client, status_for, variants, classifier,
                 progress=lambda n, t, d: error(f"  [{n}/{t}] {d}"), phase1_for=phase1_for, read_table=read_table,
                 body_tables=args.lampiran_tables, note=lambda line: error(f"  {line}"))
    md = markdown_report(h, meta)
    name = "draf_backtest" + ("_fase1_llm" if args.phase1_llm else "") + ("" if args.llm else "_tanpa_llm")
    write_report(args.output, name, md, {"meta": meta, **h})
    print(md)
    return 1 if any(r["salah_lolos"] for r in h["run"]) else 0


def register(sub) -> None:
    dt = sub.add_parser(
        "draft-rates",
        help="Fase 2: ekstrak angka tarif dari teks peraturan baru menjadi draf_tarif_YYYY.yaml + laporan diff. "
        "Tidak pernah menulis ke taxagent/taxes/pph21/data/. Exit code: 0 tidak ada perubahan, 1 ada perubahan atau ditahan gerbang, "
        "3 gagal/ditolak",
    )
    dt.add_argument("--year", type=int, default=None,
                    help="Tahun pajak draf (default: dari teks, bila berlaku sejak 1 Januari)")
    dt.add_argument("--source", action="append", default=None,
                    help="Teks peraturan: berkas .txt/.pdf/.htm atau URL unduhan JDIH (boleh berulang)")
    dt.add_argument("--note", type=int, default=None, metavar="NOMOR",
                    help="Nomor catatan efek Fase 1 (pph21 monitor-review): teks dan key diambil dari catatan")
    dt.add_argument("--status", default="monitor_state/status.json", help="Status pemantau untuk --note")
    dt.add_argument("--llm", action="store_true", help="Ekstraktor kedua (LLM) untuk gerbang G4")
    dt.add_argument("--no-ocr", action="store_true",
                    help="Jangan OCR ulang PDF scan (default: PaddleOCR lewat env ocr_gpu, hasil di-cache di "
                    "outputs/ocr_berkas)")
    dt.add_argument("--no-table", action="store_true",
                    help="Jangan baca tabel dari PDF: tabel TER di lampiran (default: dibaca bila teks menyebut tarif "
                    "efektif bulanan/harian; OCR kotak PaddleOCR + LLM vision bila --llm) dan tabel lapisan di pasal "
                    "(default: halamannya disusun ulang per baris dari OCR kotak)")
    dt.add_argument("--provider", default=None)
    dt.add_argument("--model", default=None)
    dt.add_argument("--cache", default="outputs/cache_llm/draf.jsonl")
    dt.add_argument("--base-year", type=int, default=None,
                    help="Tabel pembanding (default: tarif tahun itu atau tahun tersedia terakhir)")
    dt.add_argument("--output", default="drafts", help="Folder draf dan laporan (di luar taxagent/taxes/pph21/data/)")
    dt.add_argument("--keys", default=None,
                    help="Key terdampak dari catatan efek Fase 1, dipisah koma (gerbang G1: key logika menahan draf)")
    dt.set_defaults(handler=cmd_draft_rates)

    rv = sub.add_parser(
        "review-draft",
        help="Tahap 11: halaman review 'putuskan dulu' untuk draf tarif (reviewer mengisi angka sendiri sebelum melihat "
        "draf), atau --decision: proses keputusan menjadi patch_tarif_YYYY.yaml (tidak menulis ke taxagent/taxes/pph21/data)",
    )
    rv.add_argument("--draft", required=True, help="draf_tarif_YYYY.json dari draft-rates")
    rv.add_argument("--decision", default=None, help="keputusan_review_YYYY.json yang diekspor dari halaman review")
    rv.add_argument("--output", default=None, help="Folder halaman/patch (default: folder draf)")
    rv.add_argument("--insert", type=int, default=0,
                    help="Uji kesalahan sisipan: N kartu tambahan dengan angka draf sengaja salah (evaluasi)")
    rv.add_argument("--seed", type=int, default=0)
    rv.set_defaults(handler=cmd_review_draft)

    de = sub.add_parser(
        "draft-evaluate",
        help="Evaluasi Fase 2: replay ekstraksi + mutasi terhadap data/draf_label.yaml. "
        "Exit code: 0 tidak ada draf salah yang lolos gerbang, 1 ada, 3 gagal",
    )
    de.add_argument("--text-dataset", required=True, help="pajak_details.json aplikasi utama")
    de.add_argument("--llm", action="store_true", help="Jalankan ekstraktor kedua (LLM) untuk gerbang G4")
    de.add_argument("--provider", default=None)
    de.add_argument("--model", default=None)
    de.add_argument("--cache", default="outputs/cache_llm/draf.jsonl")
    de.add_argument("--parallel", type=int, default=4)
    de.add_argument("--no-mutation", action="store_true", help="Hanya replay ekstraksi")
    de.add_argument("--lampiran-tables", action="store_true",
                    help="Baca tabel dari PDF JDIH lokal: TER lampiran (OCR kotak; + LLM vision dengan --llm) dan "
                    "tabel lapisan di pasal (disusun ulang per baris dari OCR kotak)")
    de.add_argument("--vision-cache", default="outputs/cache_llm/visi.jsonl",
                    help="Cache jawaban LLM vision (JSONL)")
    de.add_argument("--no-graph", action="store_true",
                    help="Jangan tanya graf peraturan untuk G8 (G8 tidak dijalankan: semua draf berubah ditahan)")
    de.add_argument("--g8-now", action="store_true",
                    help="G8 memakai status peraturan hari ini (bukan saat dokumen terbit): uji bahwa peraturan yang "
                         "sudah dicabut tidak pernah menghasilkan draf siap")
    de.add_argument("--pair", choices=["pola+llm", "graf+pola", "graf+llm"], default="pola+llm",
                    help="Dua ekstraktor gerbang G4 (graf = LLM lewat bukti graf; graf+llm = tanpa regex)")
    de.add_argument("--second-model", default="gpt-4.1-mini", help="Deployment LLM kedua untuk pasangan graf+llm")
    de.add_argument("--output", default="outputs")
    de.set_defaults(handler=cmd_draft_evaluate)

    bt = sub.add_parser(
        "draft-backtest",
        help="Backtest temporal: sistem dibekukan sehari sebelum setiap perubahan nyata (data/peristiwa_backtest.yaml), "
        "lalu dihadapkan pada peraturan berikutnya (teks asli dan mutasi x1,2). Exit code: 0 tidak ada salah lolos, 1 ada",
    )
    bt.add_argument("--text-dataset", required=True, help="pajak_details.json aplikasi utama")
    bt.add_argument("--llm", action="store_true", help="Ekstraktor kedua (G4) dan lengan LLM pemantau")
    bt.add_argument("--provider", default=None)
    bt.add_argument("--model", default=None)
    bt.add_argument("--cache", default="outputs/cache_llm/draf.jsonl")
    bt.add_argument("--monitor-cache", default="outputs/cache_llm/pantau.jsonl")
    bt.add_argument("--no-mutation", action="store_true", help="Hanya teks asli")
    bt.add_argument("--no-graph", action="store_true", help="G8 tidak dijalankan")
    bt.add_argument("--pair", choices=["pola+llm"], default="pola+llm")
    bt.add_argument("--output", default="outputs")
    bt.add_argument("--lampiran-tables", action="store_true",
                    help="Baca tabel dari PDF JDIH lokal seperti draft-rates: TER lampiran (OCR kotak env ocr_gpu; + LLM "
                    "vision dengan --llm) dan tabel lapisan di pasal (disusun ulang per baris dari OCR kotak)")
    bt.add_argument("--vision-cache", default="outputs/cache_llm/visi.jsonl",
                    help="Cache jawaban LLM vision (JSONL)")
    bt.add_argument("--cumulative", action="store_true",
                    help="Replay kumulatif tanpa manusia: tabel pembanding tiap langkah = keluaran sistem sendiri")
    bt.add_argument("--phase1-llm", action="store_true",
                    help="Kunci Fase 1 dari analisis dampak kaskade (bukan label); dokumen yang tidak masuk antrean "
                    "pemantau tidak diproses")
    bt.add_argument("--impact-cache", default="outputs/cache_llm/dampak.jsonl")
    bt.set_defaults(handler=cmd_draft_backtest)
