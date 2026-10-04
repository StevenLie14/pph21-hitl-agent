from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

from ..environment import load_env, load_neo4j_env
from ..paths import DATA
from ._common import EXIT_FAILED, error, write_report


def _set_file(args) -> Path | None:
    return Path(args.file) if args.file else None


def _binary_line(prefix: str, s) -> str:
    precision = "-" if s.precision is None else f"{100 * s.precision:.1f}%"
    recall = "-" if s.recall is None else f"{100 * s.recall:.1f}%"
    return f"{prefix} presisi={precision} recall={recall}"


def trace(message: str) -> None:
    print(f"[{datetime.datetime.now():%H:%M:%S}] {message}", file=sys.stderr, flush=True)


def _llm_judge(args, graph):
    load_env()
    try:
        from ..monitor.classify_llm import LLMCache, LLMClassifier, keyword_excerpt, langchain_call
        from ..monitor.impact import MeteredClient, metered_langchain_call

        cache = LLMCache(Path(args.llm_cache))
        call, model_id = langchain_call(args.llm_provider, args.llm_model)
        classifier = LLMClassifier.with_keyword_text(call, model_id, cache)

        def judge(ident, title, subject, text):
            return classifier.classify(ident, title, subject, keyword_excerpt(text))

        client = None
        if graph is not None:
            metered_call, metered_model = metered_langchain_call(args.llm_provider, args.llm_model)
            client = MeteredClient(metered_call, metered_model, cache)
        return judge, client, None
    except Exception as e:  # noqa: BLE001
        return None, None, f"--llm diminta tetapi LLM tidak bisa dipakai ({type(e).__name__}: {e}); hanya aturan dan graf"


def _monitor_ocr():
    from ..monitor.ocr import ocr_if_scanned

    return ocr_if_scanned


def cmd_monitor(args) -> int:
    from ..monitor import SourceError, fetch_feed, load, parse_feed, run, save, text_report
    from ..monitor.run import CODE_FAILED as MONITOR_FAILED
    from ..monitor.run import fail, weekly_due
    from ..monitor.sources import fetch as fetch_url

    status_file = Path(args.status)
    try:
        status = load(status_file)
    except (ValueError, json.JSONDecodeError) as e:
        print(text_report(fail(f"berkas status {status_file} tidak bisa dibaca: {e}")))
        return MONITOR_FAILED
    try:
        documents = parse_feed(Path(args.feed_file).read_bytes()) if args.feed_file else fetch_feed(args.feed_url)
    except (SourceError, OSError) as e:
        print(text_report(fail(str(e))))
        return MONITOR_FAILED

    now = datetime.datetime.now().isoformat(timespec="seconds")
    online = not args.feed_file and not args.no_enrichment
    graph_note = None
    trace(f"feed JDIH: {len(documents)} dokumen")
    if args.graph and online:
        try:
            ingested, problems = graph_ingest([d.slug for d in documents if not d.artikel], 2, dry_run=False, redo=False,
                                              quality=True, log="monitor_state/graf_masuk.jsonl")
            written = [m for m in ingested if "dilewati" not in m]
            graph_note = (f"graf: {len(written)} peraturan dimasukkan"
                          + (f"; galat graf-masuk: {'; '.join(problems)[:300]}" if problems else ""))
        except Exception as e:  # noqa: BLE001
            graph_note = f"galat graf-masuk: neo4j-v2 tidak bisa diperbarui ({type(e).__name__}: {str(e)[:120]})"

    trace(graph_note or "graf-masuk tidak dijalankan")
    graph = None
    if not args.no_impact:
        from ..monitor.impact import build_graph

        graph = build_graph()
    judge = client = llm_note = None
    if args.llm:
        judge, client, llm_note = _llm_judge(args, graph)

    trace("klasifikasi dan pengayaan")
    result = run(
        documents,
        status,
        now=now,
        fetch=fetch_url if online else None,
        watchlist_check=online and (args.check_watchlist or weekly_due(status.watchlist_terakhir, now)),
        bpk_check=online and not args.no_bpk and weekly_due(status.bpk_terakhir, now),
        stale_check=not args.no_stale_check,
        llm_judge=judge,
        graph=graph,
        impact_client=client,
        ocr=None if args.no_ocr or not online else _monitor_ocr(),
    )
    if llm_note:
        result.warnings.append(llm_note)
        result.set_code()
    from ..agent.stale_reports import monitor_warnings

    requests = monitor_warnings()
    if requests:
        result.warnings += requests
        result.set_code()
    if graph_note and "galat graf-masuk" in graph_note:
        result.warnings.append(graph_note)
        result.set_code()
    elif graph_note:
        print(graph_note)
    if not args.no_save:
        save(status, status_file)
    if args.json:
        print(json.dumps({
            "kode_keluar": result.exit_code,
            "dokumen_baru": len(result.new_documents),
            "artikel_dibuang": result.dropped_articles,
            "pertama_kali": result.first_run,
            "galat": result.errors,
            "peringatan": result.warnings,
            "catatan_baru": [asdict(c) for c in result.new_notes],
        }, ensure_ascii=False, indent=2))
    else:
        print(text_report(result))
    return result.exit_code


def cmd_monitor_review(args) -> int:
    from ..monitor import load, save
    from ..monitor.review import list_notes, mark, summarize

    status_file = Path(args.status)
    if not status_file.exists():
        error(f"berkas status {status_file} belum ada; jalankan `pph21 monitor` dulu")
        return 1
    status = load(status_file)
    if args.mark is None:
        items = list_notes(status, include_all=args.all)
        if not items:
            print("Antrean review kosong." if not args.all else "Belum ada catatan efek.")
            return 0
        print("\n\n".join(summarize(n, c) for n, c in items))
        return 0

    if not args.verdict:
        error("--mark butuh --verdict relevan|tidak_relevan|diterapkan")
        return 1
    try:
        c, advanced = mark(
            status, args.mark, args.verdict,
            date=datetime.date.today().isoformat(),
            articles=args.article, applies_to=args.applies_to, note=args.note,
            provenance_file=Path(args.provenance) if args.provenance else None,
        )
    except ValueError as e:
        error(e)
        return 1
    save(status, status_file)
    print(summarize(args.mark, c))
    if advanced:
        print(f"terakhir_dicek dimajukan untuk: {', '.join(advanced)}")
    if c.status_review == "relevan":
        print("Catatan: data belum diubah. Terapkan ke tarif_*.yaml lalu tandai --verdict diterapkan.")
    return 0


def _feed_sample(args, out_dir: Path):
    from ..monitor import SourceError, fetch_feed
    from ..monitor.evaluation import enrichment_sample
    from ..monitor.sources import fetch as fetch_url
    from ..monitor.sources import fetch_cached

    try:
        documents = fetch_feed()
    except SourceError as e:
        error(f"feed tidak bisa diambil: {e}")
        return None
    fetcher = fetch_cached(fetch_url, out_dir / "cache_jdih") if args.cache else fetch_url
    records = enrichment_sample(documents, fetcher, args.limit, progress=lambda n, d: error(f"  [{n}] {d.identity}"))
    (out_dir / "pantau_sampel_pengayaan.json").write_text(json.dumps(records, ensure_ascii=False, indent=1),
                                                          encoding="utf-8")
    return records


def cmd_monitor_evaluate(args) -> int:
    from ..monitor.evaluation import enrichment_stats, evaluate, markdown_report, status_latency, summary_json

    results = evaluate(_set_file(args), prevent_leak=not args.no_leak_guard, since=args.since)
    if args.since:
        print(f"Uji prospektif: hanya peraturan bertanggal >= {args.since}")
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    records = None
    if args.enrichment:
        records = json.loads(Path(args.enrichment).read_text(encoding="utf-8"))
    elif args.sample_feed:
        records = _feed_sample(args, out_dir)
        if records is None:
            return 1
    stats = enrichment_stats(records) if records else None
    if args.status and Path(args.status).exists():
        from ..monitor import load

        lat = status_latency(load(Path(args.status)).catatan)
        stats = (stats or {}) | {"latensi_first_seen_hari": sorted(lat)}

    report_name = f"pantau_evaluasi_sejak_{args.since}" if args.since else "pantau_evaluasi"
    md = markdown_report(results, stats)
    summary = summary_json(results, stats)
    if args.since:
        head, _, rest = md.partition("\n")
        md = f"{head}\n\nUji prospektif: aturan pemantau beku; hanya peraturan bertanggal >= {args.since}.\n{rest}"
        summary = {"sejak": args.since, **summary}
    report = write_report(out_dir, report_name, md, summary)
    for name, h in results.items():
        s = h.binary()
        print(_binary_line(f"{name:10} n={len(h.predictions):5} positif={s.tp + s.fn:3} ditandai={s.tp + s.fp:3}", s))
    print(f"Laporan: {report}")
    return 0


def cmd_monitor_evaluate_llm(args) -> int:
    load_env()
    from ..agent import MissingApiKey
    from ..monitor.classify_llm import (
        KEYWORD_TEXT_PROMPT_VERSION,
        PROMPT_VERSION,
        TEXT_PROMPT_VERSION,
        TOOLS_PROMPT_VERSION,
        LLMCache,
        LLMClassifier,
        LLMToolClassifier,
        langchain_call,
    )
    from ..monitor.evaluation import (
        Prediction,
        SetResult,
        combine_or,
        comparison_report_md,
        comparison_summary_json,
        evaluate,
        load_set,
        score_llm,
    )

    all_sets = load_set(_set_file(args))
    chosen = args.set or list(all_sets)
    unknown = [s for s in chosen if s not in all_sets]
    if unknown:
        error(f"set tidak dikenal: {', '.join(unknown)} (ada: {', '.join(all_sets)})")
        return EXIT_FAILED
    try:
        call, model_id = langchain_call(args.provider, args.model)
    except (MissingApiKey, ImportError) as e:
        error(e)
        return 1
    cache = LLMCache(Path(args.cache))
    rule_results = evaluate(_set_file(args))

    def truncate(h: SetResult) -> SetResult:
        return SetResult(h.name, h.predictions[: args.limit] if args.limit else list(h.predictions))

    def progress(n, t):
        if n % 50 == 0 or n == t:
            error(f"  {n}/{t}")

    arms: dict[str, dict[str, SetResult]] = {}
    for spec in args.predictions or []:
        name, path = spec.split("=", 1)
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        arms[name] = {ns: SetResult(ns, [Prediction(p.item, data[ns][p.item.id], [])
                                         for p in truncate(rule_results[ns]).predictions]) for ns in chosen}
    arms["aturan"] = {ns: truncate(rule_results[ns]) for ns in chosen}
    set_items = {ns: [p.item for p in arms["aturan"][ns].predictions] for ns in chosen}

    repeats: dict[str, list[SetResult]] = {ns: [] for ns in chosen}
    for u in range(args.repeats):
        classifier = LLMClassifier(call, model_id, cache, repeats=u)
        for ns in chosen:
            error(f"LLM ulangan {u}, set {ns}: {len(set_items[ns])} item")
            repeats[ns].append(score_llm(set_items[ns], classifier, args.parallel, progress=progress))
    arms["llm"] = {ns: repeats[ns][0] for ns in chosen}
    arms["hibrida"] = {ns: combine_or(arms["aturan"][ns], arms["llm"][ns]) for ns in chosen}

    text_coverage = {}
    text_repeats: dict[str, list[SetResult]] = {ns: [] for ns in chosen}
    keyword_repeats: dict[str, list[SetResult]] = {ns: [] for ns in chosen}
    tool_results: dict[str, SetResult] = {}
    if args.text_dataset:
        from ..corpus.text_source import CorpusIndex, jdih_first
        from ..monitor.evaluation import score_article21_text, score_llm_text, texts_from_dataset

        corpus = CorpusIndex()
        texts, text_sources = {}, {}
        for ns in chosen:
            texts[ns], text_sources[ns] = jdih_first([it.id for it in set_items[ns]],
                                                     texts_from_dataset(set_items[ns], Path(args.text_dataset)), corpus)
        text_coverage = {ns: f"{len(texts[ns])}/{len(set_items[ns])}" for ns in chosen}
        arms["teks_pasal21"] = {ns: score_article21_text(set_items[ns], texts[ns]) for ns in chosen}
        for u in range(args.text_repeats):
            classifier = LLMClassifier.with_text(call, model_id, cache, repeat=u)
            for ns in chosen:
                error(f"LLM+teks ulangan {u}, set {ns}: {len(texts[ns])} item berteks")
                title_results = repeats[ns][u if u < len(repeats[ns]) else 0]
                text_repeats[ns].append(score_llm_text(set_items[ns], classifier, texts[ns], title_results, args.parallel, progress=progress))
        arms["llm_teks"] = {ns: text_repeats[ns][0] for ns in chosen}
        arms["aturan+llm_teks"] = {ns: combine_or(arms["aturan"][ns], arms["llm_teks"][ns]) for ns in chosen}
        from ..monitor.classify_llm import keyword_excerpt

        for u in range(args.text_repeats):
            classifier = LLMClassifier.with_keyword_text(call, model_id, cache, repeat=u)
            for ns in chosen:
                error(f"LLM+teks kata kunci ulangan {u}, set {ns}: {len(texts[ns])} item berteks")
                title_results = repeats[ns][u if u < len(repeats[ns]) else 0]
                keyword_repeats[ns].append(score_llm_text(set_items[ns], classifier, texts[ns], title_results,
                                                          args.parallel, progress=progress, cut=keyword_excerpt))
        arms["llm_teks_kunci"] = {ns: keyword_repeats[ns][0] for ns in chosen}
        arms["aturan+llm_teks_kunci"] = {ns: combine_or(arms["aturan"][ns], arms["llm_teks_kunci"][ns])
                                         for ns in chosen}
        if args.tool_arm:
            classifier = LLMToolClassifier(call, model_id, cache)
            for ns in chosen:
                error(f"LLM+alat cari/baca, set {ns}: {len(texts[ns])} item berteks")
                tool_results[ns] = score_llm_text(set_items[ns], classifier, texts[ns], repeats[ns][0], args.parallel,
                                                  progress=progress, cut=lambda t: t)
            arms["llm_alat"] = tool_results
            arms["aturan+llm_alat"] = {ns: combine_or(arms["aturan"][ns], tool_results[ns]) for ns in chosen}
    if "aturan_v1" in arms:
        arms["v1+llm"] = {ns: combine_or(arms["aturan_v1"][ns], arms["llm"][ns]) for ns in chosen}
        if "llm_teks" in arms:
            arms["v1+llm_teks"] = {ns: combine_or(arms["aturan_v1"][ns], arms["llm_teks"][ns]) for ns in chosen}

    invalid = sum(
        "(jawaban tidak valid)" in p.reasons
        for d in (*repeats.values(), *text_repeats.values(), *keyword_repeats.values(),
                  *([h] for h in tool_results.values())) for h in d for p in h.predictions
    )
    cache.close()
    if cache.write_failures:
        error(f"peringatan: {cache.write_failures} jawaban tidak tersimpan di cache (berkas terkunci)")
    meta = {
        "model": model_id, "prompt": PROMPT_VERSION, "ulangan": args.repeats, "batas per set": args.limit or "semua",
        "jawaban LLM tidak valid (masuk review, gagal aman)": invalid,
        "catatan": "aturan = classifier v2 sekarang (in-sample di pajakgoid); prompt LLM tidak disetel dari set uji",
    }
    if args.text_dataset:
        meta |= {
            "prompt teks": TEXT_PROMPT_VERSION, "prompt teks kata kunci": KEYWORD_TEXT_PROMPT_VERSION,
            **({"prompt alat": TOOLS_PROMPT_VERSION} if tool_results else {}),
            "ulangan teks": args.text_repeats,
            "cakupan teks per set": text_coverage,
            "sumber teks per set (JDIH dulu)": {ns: dict(Counter(v.values())) for ns, v in text_sources.items()},
            "catatan teks": "item tanpa teks memakai lengan judul; kandidat pelabelan pajakgoid = ditandai aturan "
            "ATAU teks menyebut Pasal 21, jadi teks_pasal21 diuntungkan",
        }
    variance = {f"{ns} (judul)": d for ns, d in repeats.items() if len(d) > 1}
    variance |= {f"{ns} (teks)": d for ns, d in text_repeats.items() if len(d) > 1}
    variance |= {f"{ns} (teks kata kunci)": d for ns, d in keyword_repeats.items() if len(d) > 1}
    report = write_report(args.output, "pantau_evaluasi_llm", comparison_report_md(arms, meta, variance or None),
                          comparison_summary_json(arms, meta))
    for ns in chosen:
        for arm, per_set in arms.items():
            s = per_set[ns].binary()
            print(_binary_line(f"{ns:10} {arm:16} ditandai={s.tp + s.fp:4} TP={s.tp:3} FP={s.fp:4} FN={s.fn:3}", s))
    print(f"Laporan: {report}")
    return 0


def cmd_monitor_impact(args) -> int:
    from ..monitor import impact_report as impact_rep
    from ..monitor.classify import load_watchlist
    from ..monitor.evaluation import load_set, texts_from_dataset, without_self
    from ..monitor.identity import canon_id
    from ..monitor.impact import (
        IMPACT_PROMPT_VERSION,
        build_graph,
        cascade_impact,
        graph_llm_impact,
        llm_impact,
        load_labels,
        rule_impact,
        union_impact,
    )
    from ._common import llm_client

    raw_labels = load_labels(Path(args.label) if args.label else None)
    items = [it for it in load_set(_set_file(args))["pajakgoid"] if it.label != "tidak_relevan"]
    if args.limit:
        items = items[: args.limit]
    from ..corpus.text_source import jdih_first

    texts, text_sources = jdih_first([it.id for it in items], texts_from_dataset(items, Path(args.text_dataset)))
    without_text = [it.id for it in items if it.id not in texts]
    items = [it for it in items if it.id in texts]
    labels = {i: set(v["key"]) for i, v in raw_labels.items() if i in {it.id for it in items}}
    not_dasar = {it.id for it in items if it.label != "dasar"}
    unlabelled = [it.id for it in items if it.label == "dasar" and it.id not in labels]
    if unlabelled:
        error(f"positif dasar tanpa label dampak: {', '.join(unlabelled)}")
        return EXIT_FAILED
    client, model_id = llm_client(args.provider, args.model, args.cache)
    if client is None:
        return 1
    from ..monitor.impact_report import ARMS

    chosen = [a.strip() for a in (args.arms or ",".join(ARMS)).split(",") if a.strip()]
    if unknown := [a for a in chosen if a not in ARMS]:
        error(f"lengan tidak dikenal: {', '.join(unknown)} (pilihan: {', '.join(ARMS)})")
        return EXIT_FAILED
    wl = load_watchlist()
    graph = build_graph(wl)

    def work(it):
        ident = canon_id(it.id)
        g, t, w = graph.without(ident), texts[it.id], without_self(wl, ident)
        arms = {
            "aturan": lambda: rule_impact(it.title, it.subject, ident, t, w, g),
            "llm": lambda: llm_impact(it.title, ident, t, client, g),
            "llm_graf": lambda: graph_llm_impact(it.title, ident, t, client, g),
            "llm_graf_saring": lambda: graph_llm_impact(it.title, ident, t, client, g, filtered=True),
            "kaskade": lambda: cascade_impact(it.title, it.subject, ident, t, w, client, g),
            "gabungan_utuh": lambda: union_impact(it.title, it.subject, ident, t, w, client, g),
        }
        return it.id, {name: arms[name]() for name in chosen}

    error(f"{len(items)} positif berteks, {len(labels)} berlabel dasar; LLM paralel {args.parallel}")
    with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as ex:
        results = dict(ex.map(work, items))
    client.cache.close()

    summary = impact_rep.summarize(results, labels, not_dasar, args.price_in, args.price_out)
    meta = {
        "model": model_id, "prompt": IMPACT_PROMPT_VERSION,
        "harga (USD per 1 juta token, asumsi)": f"masuk {args.price_in}, keluar {args.price_out}",
        "label diverifikasi": f"{sum(bool(v.get('diverifikasi')) for v in raw_labels.values())}/{len(raw_labels)}",
        "positif tanpa teks (dilewati)": without_text or "-",
        "sumber teks (JDIH dulu)": {i: text_sources[i] for i in sorted(texts)},
    }
    md = impact_rep.markdown_report(results, summary, meta, labels, not_dasar, {it.id: it.label for it in items})
    report = write_report(args.output, "pantau_dampak", md, impact_rep.to_json(results, summary, meta))
    for arm in chosen:
        print(impact_rep.console_lines(arm, summary[arm], len(results)))
    print(f"Laporan: {report}")
    return 0


SET_FILE_HELP = "Set berlabel (default taxagent/taxes/pph21/data/pantau_evaluasi.yaml)"
PROVIDER_HELP = "azure | openai (default dari kunci yang tersedia)"


JDIH_DIR = DATA / "korpus_jdih"
PAJAK_DIR = DATA / "korpus_pajak"


def graph_ingest(jdih_slugs: list[str], pajak_pages: int, *, dry_run: bool, redo: bool, quality: bool,
                 log: str, fetch=None, ocr: bool = True) -> tuple[list[dict], list[str]]:
    from ..monitor.graph_v2 import Neo4jV2Client
    from ..monitor.sources import fetch as fetch_url

    fetch = fetch or fetch_url
    skip_ocr = None
    if not ocr:
        from ..monitor.ocr import OCRResult
        from ..monitor.text_quality import pdf_kind

        def skip_ocr(content: bytes) -> OCRResult:
            return OCRResult(None, pdf_kind(content), "lapisan_pdf", "OCR dilewati (--no-ocr)")
    load_neo4j_env()
    neo = Neo4jV2Client()
    try:
        return _graph_ingest(neo, jdih_slugs, pajak_pages, dry_run=dry_run, redo=redo, quality=quality, log=log,
                             fetch=fetch, skip_ocr=skip_ocr)
    finally:
        neo.close()


def _graph_ingest(neo, jdih_slugs, pajak_pages, *, dry_run, redo, quality, log, fetch, skip_ocr):
    from ..monitor.graph_ingest import (
        ALREADY_PRESENT,
        corpus_vocabulary,
        from_jdih,
        ingest,
        is_complete,
        latest_pajak,
        local_jdih_index,
        pajak_document,
        seen_pajak_slugs,
    )
    from ..monitor.sources import SourceError

    skip_existing = None if redo else (lambda key: is_complete(neo, key))
    documents, problems, skipped = [], [], []
    for i, slug in enumerate(jdih_slugs, 1):
        trace(f"graf-masuk JDIH {i}/{len(jdih_slugs)}: {slug}")
        try:
            d = from_jdih(slug, fetch, skip_ocr, skip_existing)
        except (SourceError, OSError, RuntimeError) as e:
            problems.append(f"JDIH {slug}: {e}")
            continue
        if d is None:
            problems.append(f"JDIH {slug}: identitas tidak terbaca")
        elif ALREADY_PRESENT in d.notes:
            skipped.append({"kunci": d.key, "dilewati": "sudah ada di graf"})
        else:
            documents.append(d)
    if pajak_pages:
        try:
            seen = set() if redo else seen_pajak_slugs(PAJAK_DIR)
            index = local_jdih_index(JDIH_DIR)
            for item in latest_pajak(fetch, pajak_pages):
                if item["slug"] in seen:
                    continue
                try:
                    d = pajak_document(item, fetch, index, skip_ocr)
                except (SourceError, OSError) as e:
                    problems.append(f"pajak.go.id {item['slug']}: {e}")
                    continue
                if d is None:
                    problems.append(f"pajak.go.id {item['slug']}: identitas tidak terbaca "
                                    f"({item.get('jenis')} {item.get('nomor')})")
                elif not (d.source == "jdih" and d.id in jdih_slugs):
                    documents.append(d)
        except (SourceError, OSError) as e:
            problems.append(f"daftar pajak.go.id: {e}")
    if not documents:
        return skipped, problems
    vocabulary = corpus_vocabulary(JDIH_DIR) if quality and (JDIH_DIR / "berkas").exists() else None
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    trace(f"graf-masuk: menulis {len(documents)} dokumen")
    results = skipped + ingest(documents, neo, vocabulary=vocabulary, dry_run=dry_run, redo=redo, meta={"commit": commit})
    if not dry_run and log:
        Path(log).parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as f:
            for h in results:
                f.write(json.dumps(h, ensure_ascii=False) + "\n")
    return results, problems


def cmd_graph_ingest(args) -> int:
    from ..monitor import SourceError, fetch_feed, parse_feed

    slugs = list(args.slug or [])
    if not args.no_feed and not slugs:
        try:
            feed = parse_feed(Path(args.feed_file).read_bytes()) if args.feed_file else fetch_feed(args.feed_url)
        except (SourceError, OSError) as e:
            print(f"feed JDIH tidak bisa diambil: {e}")
            return 3
        slugs = [d.slug for d in feed if not d.artikel][:args.limit]
    try:
        results, problems = graph_ingest(slugs, args.pajak_pages, dry_run=args.dry_run, redo=args.redo,
                                         quality=not args.no_quality, log=args.log, ocr=not args.no_ocr)
    except Exception as e:  # noqa: BLE001
        print(f"graf neo4j-v2 tidak bisa ditulis/dibaca: {type(e).__name__}: {e}")
        return 3
    print(json.dumps({"dokumen": results, "galat": problems}, ensure_ascii=False, indent=1))
    return 0 if not problems else 2


def _v2_client():
    from ..monitor.graph_v2 import Neo4jV2Client

    load_neo4j_env()
    return Neo4jV2Client()


def _write_pajak_corpus(slug: str, item: dict, html: str) -> None:
    from ..corpus.pajak_go_id import parse_detail

    meta, text = parse_detail(html)
    for sub in ("html", "detail", "teks"):
        (PAJAK_DIR / sub).mkdir(parents=True, exist_ok=True)

    def write(path: Path, content: str) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)

    write(PAJAK_DIR / "html" / f"{slug}.html", html)
    if text:
        write(PAJAK_DIR / "teks" / f"{slug}.txt", text)
    write(PAJAK_DIR / "detail" / f"{slug}.json",
          json.dumps({**item, **meta, "panjang_teks": len(text)}, ensure_ascii=False, indent=1))


def pajak_sweep(*, dry_run: bool, max_pages: int | None, max_ingest: int, ocr: bool, log: str,
                output_dir: str, fetch=None, client=None, echo=print) -> dict:
    from ..corpus.merge import listing_id as listing_key
    from ..monitor.graph_ingest import ingest, local_jdih_index, pajak_document, safe_url
    from ..monitor.pajak_sweep import (
        FIELDS,
        became_inactive,
        compare,
        load_snapshot,
        reason,
        save_snapshot,
        sweep,
    )
    from ..monitor.sources import SourceError
    from ..monitor.sources import fetch as fetch_url

    fetch = fetch or fetch_url
    skip_ocr = None
    if not ocr:
        from ..monitor.ocr import OCRResult
        from ..monitor.text_quality import pdf_kind

        def skip_ocr(content: bytes) -> OCRResult:
            return OCRResult(None, pdf_kind(content), "lapisan_pdf", "OCR dilewati (--no-ocr)")
    snapshot = load_snapshot(PAJAK_DIR)
    items, failed_pages = sweep(fetch, max_pages, echo)
    new, changed = compare(snapshot, items)
    echo(f"listing: {len(items)} slug, {len(new)} baru, {len(changed)} berubah, {len(failed_pages)} halaman gagal")
    index = local_jdih_index(JDIH_DIR)
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    close_client = client is None
    client = client or _v2_client()
    results, findings, problems, processed = [], [], [], 0
    if max_pages is None and len(items) < 0.9 * len(snapshot):
        problems.append(f"listing hanya {len(items)} slug, potret {len(snapshot)}: periksa parser/listing pajak.go.id")
    try:
        queue = [(x, None) for x in new] + list(changed)
        for x, diff in queue:
            if processed >= max_ingest:
                problems.append(f"batas --max-ingest {max_ingest} tercapai; {len(queue) - processed} slug "
                                "menunggu sapu berikutnya")
                break
            processed += 1
            cause = (f"sapu: slug baru di halaman listing {x['halaman_listing']}" if diff is None
                     else f"sapu: {reason(diff)}")
            ident = listing_key(x.get("jenis") or "", x.get("nomor") or "")
            node = None
            if ident is not None:
                q = client.query("MATCH (p:Regulation {key: $k}) OPTIONAL MATCH (a:Regulation)-[e:MENCABUT]->(p) "
                                 "WHERE e.evidence IN ['eksplisit', 'tersirat'] RETURN p.doc_source AS sumber, p.has_text AS teks, count(e) AS pencabut",
                                 k=str(ident))
                node = q[0] if q else None
            if diff and became_inactive(diff) and not (node and node.get("pencabut")):
                findings.append({"slug": x["slug"], "kunci": str(ident) if ident else None, "nomor": x.get("nomor"),
                                 "alasan": reason(diff),
                                 "temuan": "label pajak.go.id menjadi tidak berlaku, graf belum punya pencabut berbukti"})
            d = None
            try:
                html = fetch(safe_url(x["url"])).decode("utf-8", "ignore")
                if diff is not None and node and node.get("sumber") == "jdih" and node.get("teks"):
                    results.append({"kunci": str(ident), "slug": x["slug"], "dilewati": "node dari JDIH berteks",
                                    "alasan": cause})
                else:
                    d = pajak_document(x, fetch, index, skip_ocr, html=html)
                if not dry_run:
                    _write_pajak_corpus(x["slug"], {k: v for k, v in x.items() if k != "halaman_listing"}, html)
            except (SourceError, OSError) as e:
                problems.append(f"pajak.go.id {x['slug']}: {e}")
                continue
            if d is None and diff is None:
                problems.append(f"pajak.go.id {x['slug']}: identitas tidak terbaca ({x.get('jenis')} {x.get('nomor')})")
            if d is not None:
                [h] = ingest([d], client, dry_run=dry_run, redo=diff is not None,
                             meta={"commit": commit, "alasan": cause})
                results.append({**h, "slug": x["slug"], "alasan": cause})
            if not dry_run:
                snapshot[x["slug"]] = {k: x.get(k, "") for k in FIELDS}
                if diff is None:
                    with open(PAJAK_DIR / "daftar.jsonl", "a", encoding="utf-8") as f:
                        f.write(json.dumps({k: v for k, v in x.items() if k != "halaman_listing"},
                                           ensure_ascii=False) + "\n")
        if not dry_run:
            new_slugs = {x["slug"] for x in new}
            for x in items:
                if x["slug"] not in new_slugs:
                    snapshot.setdefault(x["slug"], {k: x.get(k, "") for k in FIELDS})
            save_snapshot(PAJAK_DIR, snapshot)
    finally:
        if close_client:
            client.close()
    listed = {x["slug"] for x in items}
    missing = ([k for k in snapshot if k not in listed] if max_pages is None and not failed_pages else [])
    report = {"waktu": datetime.datetime.now().isoformat(timespec="seconds"), "kering": dry_run,
              "slug_listing": len(items), "baru": len(new), "berubah": len(changed), "diproses": processed,
              "slug_baru": [{k: x.get(k) for k in ("slug", "nomor", "jenis", "tanggal", "halaman_listing")}
                            for x in new][:200],
              "slug_hilang": missing[:200],
              "halaman_gagal": failed_pages, "dokumen": results, "temuan": findings, "galat": problems}
    if not dry_run:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        (Path(output_dir) / f"sapu_pajak_{datetime.date.today():%Y%m%d}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        if log:
            with open(log, "a", encoding="utf-8") as f:
                for h in results:
                    f.write(json.dumps(h, ensure_ascii=False) + "\n")
    return report


def cmd_pajak_sweep(args) -> int:
    from ..monitor.sources import SourceError

    try:
        report = pajak_sweep(dry_run=args.dry_run, max_pages=args.max_pages, max_ingest=args.max_ingest,
                             ocr=not args.no_ocr, log=args.log, output_dir=args.output)
    except (SourceError, OSError) as e:
        print(f"listing pajak.go.id tidak bisa diambil: {e}")
        return 3
    except Exception as e:  # noqa: BLE001
        print(f"graf neo4j-v2 tidak bisa ditulis/dibaca: {type(e).__name__}: {e}")
        return 3
    summary = {k: report[k] for k in ("slug_listing", "baru", "berubah", "diproses", "halaman_gagal", "slug_baru",
                                      "slug_hilang")}
    print(json.dumps({**summary, "temuan": report["temuan"], "galat": report["galat"]}, ensure_ascii=False, indent=1))
    if report["temuan"]:
        return 1
    return 2 if report["galat"] or report["halaman_gagal"] else 0


def cmd_agent_requests(args) -> int:
    from ..agent import stale_reports as P

    if args.mark is None:
        items = P.open_reports() if not args.all else [r for r in P.load() if r.get("jenis") != "tandai"]
        if not items:
            print("Tidak ada permintaan agent yang terbuka.")
            return 0
        for r in items:
            print(f"#{r['nomor']} {r['tanggal']} {r['alasan']} {r['objek']} (fakta {r['tanggal_fakta']})\n"
                  f"  {r['keterangan']}\n  bukti: {json.dumps(r['bukti'], ensure_ascii=False)}")
        return 0
    if not args.verdict:
        error("--mark butuh --verdict")
        return 1
    try:
        P.resolve(args.mark, args.verdict, args.note or "")
    except ValueError as e:
        error(str(e))
        return 1
    print(f"permintaan #{args.mark} ditandai {args.verdict}")
    return 0


def register(sub) -> None:
    pn = sub.add_parser(
        "monitor",
        help="Deteksi peraturan baru yang berdampak pada PPh 21 (feed JDIH Kemenkeu). "
        "Exit code: 0 tidak ada, 1 ada temuan, 2 peringatan, 3 pemantau gagal",
    )
    pn.add_argument("--status", default="monitor_state/status.json", help="Berkas status (dokumen terlihat, catatan efek)")
    pn.add_argument("--feed-url", default="https://jdih.kemenkeu.go.id/feed.json")
    pn.add_argument("--feed-file", default=None, help="Pakai feed JSON lokal (uji/offline) alih-alih mengambil dari internet")
    pn.add_argument("--json", action="store_true", help="Keluaran JSON")
    pn.add_argument("--no-save", action="store_true", help="Jangan perbarui berkas status")
    pn.add_argument("--no-enrichment", action="store_true",
                    help="Jangan ambil halaman/teks JDIH untuk dokumen baru (hanya klasifikasi judul)")
    pn.add_argument("--check-watchlist", action="store_true", help="Paksa cek relasi halaman watchlist (default: mingguan)")
    pn.add_argument("--no-bpk", action="store_true", help="Lewati jaring pengaman sitemap BPK mingguan")
    pn.add_argument("--no-stale-check", action="store_true",
                    help="Lewati peringatan basi (provenans, fasilitas habis, tarif tahun berjalan, feed sepi, antrean)")
    pn.add_argument("--llm", action="store_true",
                    help="Pendapat kedua LLM + teks untuk setiap dokumen baru (masuk review bila aturan ATAU LLM menandai) "
                    "dan kaskade LLM + graf pada analisis dampak. Butuh kunci LLM; tanpa kunci pemantau tetap jalan (exit 2)")
    pn.add_argument("--llm-provider", default=None, help=PROVIDER_HELP)
    pn.add_argument("--llm-model", default=None, help="Nama model/deployment")
    pn.add_argument("--llm-cache", default="monitor_state/cache_llm.jsonl", help="Cache jawaban LLM pemantau")
    pn.add_argument("--no-impact", action="store_true", help="Lewati analisis dampak lewat graf")
    pn.add_argument("--no-ocr", action="store_true",
                    help="Baca PDF scan dari lapisan teks, bukan OCR (cuplikan LLM dan dampak memakai teks rusak)")
    pn.add_argument("--graph", action="store_true",
                    help="Masukkan dokumen baru feed (dan daftar terbaru pajak.go.id) ke graf lengkap neo4j-v2 "
                    "sebelum analisis dampak (lihat graph-ingest)")
    pn.set_defaults(handler=cmd_monitor)

    gm = sub.add_parser(
        "graph-ingest",
        help="Masukkan peraturan baru (feed JDIH, daftar terbaru pajak.go.id) ke graf lengkap neo4j-v2 tanpa bangun "
        "ulang: teks, cek mutu, relasi berbukti, potongan per pasal, status. Exit code: 0 ok, 2 ada galat, 3 gagal",
    )
    gm.add_argument("--slug", action="append", help="Slug halaman JDIH (/dok/<slug>); boleh berulang. Default: isi feed")
    gm.add_argument("--feed-url", default="https://jdih.kemenkeu.go.id/feed.json")
    gm.add_argument("--feed-file", default=None)
    gm.add_argument("--limit", type=int, default=50, help="Maksimal dokumen feed yang diperiksa")
    gm.add_argument("--no-feed", action="store_true", help="Jangan ambil feed JDIH (mis. hanya pajak.go.id)")
    gm.add_argument("--pajak-pages", type=int, default=2,
                    help="Halaman teratas daftar pajak.go.id yang diperiksa (0 = lewati pajak.go.id)")
    gm.add_argument("--dry-run", action="store_true", help="Susun paket dan baca graf, tanpa menulis")
    gm.add_argument("--redo", action="store_true", help="Proses juga dokumen yang sudah ada di graf / korpus")
    gm.add_argument("--no-ocr", action="store_true",
                    help="Jangan OCR PDF scan (mis. saat GPU dipakai OCR korpus); dokumen scan masuk tanpa teks")
    gm.add_argument("--no-quality", action="store_true", help="Lewati cek mutu (kosakata acuan dari korpus JDIH)")
    gm.add_argument("--log", default="monitor_state/graf_masuk.jsonl", help="Log setiap pemasukan (untuk telusur/batal)")
    gm.set_defaults(handler=cmd_graph_ingest)

    sp = sub.add_parser(
        "pajak-sweep",
        help="Sapu seluruh listing pajak.go.id (mingguan): slug baru di halaman mana pun dan slug yang label status, "
        "tanggal, atau judulnya berubah dimasukkan (ulang) ke neo4j-v2, JDIH tetap sumber utama. "
        "Exit code: 0 ok, 1 ada temuan label, 2 ada galat, 3 gagal",
    )
    sp.add_argument("--dry-run", action="store_true", help="Telusur dan bandingkan, tanpa menulis graf/korpus/potret")
    sp.add_argument("--max-pages", type=int, default=None, help="Batasi halaman listing (uji coba)")
    sp.add_argument("--max-ingest", type=int, default=300, help="Maksimal slug yang dimasukkan per sapu")
    sp.add_argument("--no-ocr", action="store_true", help="Jangan OCR PDF scan (lampiran atau berkas JDIH)")
    sp.add_argument("--log", default="monitor_state/graf_masuk.jsonl")
    sp.add_argument("--output", default="monitor_state", help="Folder laporan sapu_pajak_YYYYMMDD.json")
    sp.set_defaults(handler=cmd_pajak_sweep)

    pr = sub.add_parser("monitor-review", help="Tampilkan dan tandai antrean review catatan efek pemantau")
    pr.add_argument("--status", default="monitor_state/status.json")
    pr.add_argument("--all", action="store_true", help="Tampilkan juga yang sudah selesai direview")
    pr.add_argument("--mark", type=int, default=None, metavar="NOMOR", help="Nomor catatan (lihat daftar)")
    pr.add_argument("--verdict", choices=["relevan", "tidak_relevan", "diterapkan"], default=None)
    pr.add_argument("--article", action="append", default=None, help="Pasal terdampak (boleh berulang)")
    pr.add_argument("--applies-to", action="append", default=None, help="Mis. 'Tahun Pajak 2027' (boleh berulang)")
    pr.add_argument("--note", default=None, help="Catatan reviewer")
    pr.add_argument("--provenance", default=None, help=argparse.SUPPRESS)
    pr.set_defaults(handler=cmd_monitor_review)

    pa = sub.add_parser("agent-requests", help="Tampilkan dan tandai permintaan pemeriksaan dari agent "
                        "(report_possibly_stale); yang terbuka ikut jadi peringatan `pph21 monitor`")
    pa.add_argument("--all", action="store_true", help="Tampilkan juga yang sudah ditandai")
    pa.add_argument("--mark", type=int, default=None, metavar="NOMOR")
    pa.add_argument("--verdict", choices=["ditindaklanjuti", "tidak_perlu"], default=None)
    pa.add_argument("--note", default=None)
    pa.set_defaults(handler=cmd_agent_requests)

    pe = sub.add_parser(
        "monitor-evaluate",
        help="Presisi/recall classifier pemantau pada set berlabel, plus latensi dan selisih teks vs metadata JDIH",
    )
    pe.add_argument("--file", default=None, help=SET_FILE_HELP)
    pe.add_argument("--output", default="outputs", help="Folder laporan Markdown dan JSON")
    pe.add_argument("--enrichment", default=None, help="Rekaman sampel pengayaan JSON yang sudah ada")
    pe.add_argument("--sample-feed", action="store_true", help="Ambil feed JDIH sekarang dan perkaya setiap peraturannya (lambat)")
    pe.add_argument("--limit", type=int, default=0, help="Batasi jumlah dokumen sampel (0 = semua)")
    pe.add_argument("--cache", action="store_true", help="Simpan unduhan JDIH di <keluaran>/cache_jdih untuk diulang")
    pe.add_argument("--status", default=None, help="Berkas status pemantau untuk latensi first_seen - diundangkan")
    pe.add_argument("--no-leak-guard", action="store_true",
                    help="Izinkan dokumen dicocokkan dengan entri watchlist dirinya sendiri")
    pe.add_argument("--since", default=None, metavar="YYYY-MM-DD",
                    help="Uji prospektif: hanya peraturan bertanggal pada/sesudah tanggal beku aturan pemantau")
    pe.set_defaults(handler=cmd_monitor_evaluate)

    pl = sub.add_parser(
        "monitor-evaluate-llm",
        help="Eksperimen: classifier aturan vs LLM vs hibrida (aturan ATAU LLM) pada set berlabel yang sama, "
        "dengan McNemar berpasangan. Exit code: 0 selesai, 1 kunci API tidak ada, 3 argumen salah",
    )
    pl.add_argument("--file", default=None, help=SET_FILE_HELP)
    pl.add_argument("--set", action="append", default=None, help="Set yang dinilai (boleh berulang; default semua)")
    pl.add_argument("--limit", type=int, default=0, help="Hanya N item pertama per set (uji coba; 0 = semua)")
    pl.add_argument("--provider", default=None, help=PROVIDER_HELP)
    pl.add_argument("--model", default=None, help="Nama model/deployment (default dari environment)")
    pl.add_argument("--parallel", type=int, default=4, help="Jumlah panggilan LLM bersamaan")
    pl.add_argument("--repeats", type=int, default=1, help="Ulangi seluruh run N kali untuk mengukur variansi")
    pl.add_argument("--cache", default="outputs/cache_llm/klasifikasi.jsonl", help="Cache jawaban LLM (JSONL)")
    pl.add_argument("--predictions", action="append", default=None,
                    help="Lengan tambahan dari berkas prediksi: nama=berkas.json ({set: {id: kategori}})")
    pl.add_argument("--text-dataset", default=None,
                    help="pajak_details.json aplikasi utama: tambah lengan teks_pasal21 dan llm_teks (cuplikan teks)")
    pl.add_argument("--text-repeats", type=int, default=1, help="Ulangan lengan LLM+teks (lebih mahal per panggilan)")
    pl.add_argument("--tool-arm", action="store_true",
                    help="Tambah lengan llm_alat: LLM menelusuri teks penuh dengan alat cari/baca (butuh --text-dataset)")
    pl.add_argument("--output", default="outputs", help="Folder laporan")
    pl.set_defaults(handler=cmd_monitor_evaluate_llm)

    pd = sub.add_parser(
        "monitor-impact",
        help="Eksperimen analisis dampak pada positif set pajakgoid: aturan vs LLM vs LLM + graf "
        "(key terdampak, token, biaya, latensi). Exit code: 0 selesai, 1 kunci API tidak ada, 3 label kurang",
    )
    pd.add_argument("--text-dataset", required=True, help="pajak_details.json aplikasi utama")
    pd.add_argument("--file", default=None, help=SET_FILE_HELP)
    pd.add_argument("--label", default=None, help="Label key dampak (default taxagent/taxes/pph21/data/dampak_label.yaml)")
    pd.add_argument("--limit", type=int, default=0, help="Hanya N positif pertama (uji coba)")
    pd.add_argument("--provider", default=None, help="azure | openai")
    pd.add_argument("--model", default=None, help="Nama model/deployment")
    pd.add_argument("--parallel", type=int, default=4, help="Dokumen yang diproses bersamaan")
    pd.add_argument("--arms", default=None,
                    help="Lengan dipisah koma (default semua): aturan,llm,llm_graf,llm_graf_saring,kaskade,gabungan_utuh. "
                    "Run akhir: aturan,gabungan_utuh")
    pd.add_argument("--cache", default="outputs/cache_llm/dampak.jsonl", help="Cache jawaban LLM (JSONL)")
    pd.add_argument("--price-in", type=float, default=0.40, help="USD per 1 juta token masukan (default gpt-4.1-mini)")
    pd.add_argument("--price-out", type=float, default=1.60, help="USD per 1 juta token keluaran (default gpt-4.1-mini)")
    pd.add_argument("--output", default="outputs", help="Folder laporan")
    pd.set_defaults(handler=cmd_monitor_impact)
