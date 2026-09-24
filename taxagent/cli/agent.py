from __future__ import annotations

import datetime
import fnmatch
import json
import re
from pathlib import Path

from ..environment import load_env
from ..settings import get_settings
from ._common import error


def _new_agent(**kw):
    load_env()
    from ..agent import MissingApiKey, TaxAgent

    try:
        return TaxAgent(**kw)
    except (MissingApiKey, ImportError) as e:
        error(e)
        return None


def cmd_ask(args) -> int:
    agent = _new_agent(model=args.model, verbose=args.verbose)
    if agent is None:
        return 1
    result = agent.ask(args.question)
    print(result.answer)
    if args.verbose:
        print(f"\n[{result.rounds} putaran, tool: {', '.join(result.called_tool_names()) or 'tidak ada'}]")
    return 0


def cmd_chat(args) -> int:
    agent = _new_agent(model=args.model, verbose=args.verbose)
    if agent is None:
        return 1
    print("Agent PPh 21. Ketik 'keluar' untuk berhenti.\n")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if line.lower() in {"keluar", "exit", "quit"}:
            return 0
        if line:
            print("\n" + agent.ask(line).answer + "\n")


def _model_name(provider: str, model: str | None) -> str:
    if model:
        return model
    return get_settings().model_name(provider) or "?"


def cmd_evaluate(args) -> int:
    load_env()
    from ..agent import MissingApiKey, TaxAgent
    from ..agent.runner import default_provider
    from ..evaluation import apply_original_questions, load_cases, markdown_report, run_cases, summarize, to_dicts

    cases = load_cases(args.dataset)
    n_original = apply_original_questions(cases, args.original_questions) if args.original_questions else 0
    if args.id:
        cases = [k for k in cases if fnmatch.fnmatch(k["id"], args.id)]
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        error("Tidak ada kasus yang cocok.")
        return 1

    try:
        provider = (args.provider or default_provider()).lower()
    except MissingApiKey as e:
        error(e)
        return 1
    if _new_agent(model=args.model, provider=provider) is None:
        return 1
    model = _model_name(provider, args.model)

    total = len(cases)
    counter = iter(range(1, total + 1))

    def report(h) -> None:
        mark = "BENAR" if h.perilaku_benar else "SALAH"
        detail = h.error or f"tool={h.tool_hitung_akhir or '-'} pph={h.pph_aktual or '-'}"
        print(f"[{next(counter)}/{total}] {h.id:10} {mark:5} {detail}", flush=True)

    results = run_cases(cases, lambda: TaxAgent(model=args.model, provider=provider), on_done=report,
                        retry_rounds=args.retry_rounds, round_delay=args.round_delay)
    summary = summarize(results)
    now = datetime.datetime.now()
    meta = {
        "provider": provider,
        "model": model,
        "waktu": now.isoformat(timespec="seconds"),
        "dataset": str(args.dataset or "taxagent/taxes/pph21/data/kasus_agent.yaml"),
        "n_kasus": total,
        "putaran_ulang_galat": args.retry_rounds,
    }
    if args.original_questions:
        meta["pertanyaan_asli"] = {"berkas": str(args.original_questions), "n_diganti": n_original}

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"{now:%Y%m%d-%H%M%S}_{provider}_{re.sub(r'[^A-Za-z0-9-]', '_', model)}"
    (out_dir / f"{name}.json").write_text(
        json.dumps({"meta": meta, "ringkasan": summary, "kasus": to_dicts(results)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / f"{name}.md").write_text(markdown_report(meta, summary, results), encoding="utf-8")

    calc = summary["hitung"]
    print()
    print(f"Akurasi keseluruhan : {summary['akurasi_keseluruhan']} (maks. 1 klarifikasi)")
    print(f"Akurasi satu giliran: {summary['akurasi_satu_giliran']}")
    print(f"Klarifikasi tak perlu: {summary['klarifikasi_tidak_perlu']}")
    print(f"Kasus hitung yang memanggil graf: {summary.get('kasus_hitung_memanggil_graf', 0)}")
    t = summary.get("token") or {}
    print(f"Token LLM: masuk {t.get('masuk', 0)}, keluar {t.get('keluar', 0)} (rata-rata keluar per kasus {t.get('keluar_per_kasus')})")
    print(f"Hitung - tool       : {calc['akurasi_tool']} (percobaan pertama {calc['akurasi_tool_percobaan_pertama']})")
    print(f"Hitung - argumen    : {calc['akurasi_argumen_lengkap']} (per field {calc['akurasi_field']})")
    print(f"Hitung - angka akhir: {calc['akurasi_angka_akhir']}")
    print(f"Non-hitung          : {summary['non_hitung']['per_perilaku']}")
    print(f"Laporan: {out_dir / f'{name}.md'}")
    return 0


def cmd_agent_backtest(args) -> int:
    load_env()
    from ..agent import MissingApiKey, TaxAgent
    from ..agent.runner import default_provider
    from ..evaluation import agent_backtest as A
    from ..tools.regulation_graph import ReadOnlyClient

    cases = A.load_cases(Path(args.cases) if args.cases else None)
    if args.id:
        cases = [k for k in cases if fnmatch.fnmatch(k["id"], args.id)]
    phases = tuple(args.phase) if args.phase else A.PHASES
    try:
        provider = (args.provider or default_provider()).lower()
    except MissingApiKey as e:
        error(e)
        return 1
    if _new_agent(model=args.model, provider=provider) is None:
        return 1
    model = _model_name(provider, args.model)
    backtest_runs = json.loads(Path(args.draft_backtest).read_text(encoding="utf-8"))["run"]
    own_tables = None
    if args.own_tables:
        own_tables = json.loads(Path(args.own_tables).read_text(encoding="utf-8")).get("tabel_sendiri")
        if not own_tables:
            error(f"{args.own_tables} tidak punya tabel_sendiri (jalankan draft-backtest --cumulative --phase1-llm)")
            return 1

    def report(r) -> None:
        print(f"{r.kasus} {r.fase:17} #{r.ulang} {r.hasil:22} {r.detik:6.1f}s {','.join(r.alasan_lapor) or '-'}",
              flush=True)

    h = A.run(cases, lambda: TaxAgent(model=args.model, provider=provider), ReadOnlyClient(), backtest_runs, phases,
              args.repeat, report, own_tables)
    meta = {"provider": provider, "model": model, "waktu": datetime.datetime.now().isoformat(timespec="seconds"),
            "ulang": args.repeat, "draf_backtest": args.draft_backtest}
    if args.own_tables:
        meta["tabel_sendiri"] = args.own_tables
    if args.cases:
        meta["kasus"] = args.cases
    md, _ = A.write(h, meta, Path(args.output), "backtest_agent_umpan_ke_jawaban" if own_tables else "backtest_agent")
    print(md.read_text(encoding="utf-8"))
    return 0


def register(sub) -> None:
    q = sub.add_parser("ask", help="Tanya agent sekali jalan (butuh kunci API Azure atau OpenAI)")
    q.add_argument("question")
    q.add_argument("--model", default=None)
    q.add_argument("--verbose", action="store_true")
    q.set_defaults(handler=cmd_ask)

    c = sub.add_parser("chat", help="Percakapan interaktif dengan agent")
    c.add_argument("--model", default=None)
    c.add_argument("--verbose", action="store_true")
    c.set_defaults(handler=cmd_chat)

    ev = sub.add_parser("evaluate",
                        help="Evaluasi agent gaya BFCL (pemilihan tool, argumen, angka akhir); butuh kunci API")
    ev.add_argument("--provider", choices=["azure", "openai"], default=None)
    ev.add_argument("--model", default=None, help="Nama model OpenAI atau nama deployment Azure")
    ev.add_argument("--dataset", default=None, help="Berkas YAML kasus (default taxagent/taxes/pph21/data/kasus_agent.yaml)")
    ev.add_argument("--original-questions", default=None,
                    help="YAML kalimat asli penanya di luar repo (experiments/natural_questions.py); kunci tetap dari --dataset")
    ev.add_argument("--id", default=None, help="Pola id kasus, mis. 'pen-*'")
    ev.add_argument("--limit", type=int, default=0, help="Batasi jumlah kasus (0 = semua)")
    ev.add_argument("--output", default="outputs", help="Folder laporan JSON dan Markdown")
    ev.add_argument("--retry-rounds", type=int, default=5,
                    help="Putaran ulang kasus yang masih galat API sesudah semua kasus jalan (0 = tidak)")
    ev.add_argument("--round-delay", type=float, default=60.0, help="Jeda antar putaran ulang (detik)")
    ev.set_defaults(handler=cmd_evaluate)

    ab = sub.add_parser("agent-backtest",
                        help="Backtest temporal tingkat agent: basi, sadar, teradaptasi per perubahan nilai nyata; "
                        "butuh kunci API dan graf")
    ab.add_argument("--provider", choices=["azure", "openai"], default=None)
    ab.add_argument("--model", default=None)
    ab.add_argument("--cases", default=None,
                    help="Berkas YAML kasus (default taxagent/taxes/pph21/data/kasus_backtest_agent.yaml)")
    ab.add_argument("--id", default=None, help="Pola id kasus, mis. 'a2016'")
    ab.add_argument("--phase", action="append", default=None, help="Fase tertentu (boleh berulang)")
    ab.add_argument("--repeat", type=int, default=1, help="Ulangan per fase")
    ab.add_argument("--draft-backtest", required=True,
                    help="JSON draft-backtest run akhir (keputusan pipeline dan nilai x1,2); wajib, supaya hasil "
                    "lama tidak terbaca diam-diam")
    ab.add_argument("--own-tables", default=None,
                    help="JSON draft-backtest --cumulative --phase1-llm: pakai tabel milik sistem sendiri (umpan ke "
                    "jawaban, tanpa label)")
    ab.add_argument("--output", default="outputs")
    ab.set_defaults(handler=cmd_agent_backtest)
