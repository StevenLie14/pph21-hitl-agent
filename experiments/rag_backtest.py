from __future__ import annotations

import argparse
import datetime
import json
import sys
import time
from decimal import Decimal
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from taxagent.agent.runner import AgentTurn, build_model  # noqa: E402
from taxagent.environment import load_env  # noqa: E402
from taxagent.evaluation import agent_backtest as A  # noqa: E402
from taxagent.tools.regulation_graph import ReadOnlyClient  # noqa: E402
from taxagent.update import backtest as B  # noqa: E402

SYSTEM = ("Anda asisten Pajak Penghasilan Pasal 21 Indonesia. Di bawah ini ada teks lengkap peraturan yang tersedia. "
          "Jawab pertanyaan pengguna dengan menghitung PPh 21 sesuai ketentuan yang berlaku pada tahun pajak yang "
          "ditanyakan, berdasarkan teks peraturan tersebut, dan tuliskan hasil akhirnya dalam rupiah. Sebutkan "
          "peraturan yang Anda pakai. Bila teks tidak cukup untuk memastikan ketentuan tahun pajak itu, katakan.")
RETRIES = 3
MAX_CHARS = 200_000
CURRENT: dict = {}


def mutated_text(name: str, info: dict, text: str, docs: dict) -> tuple[str, dict]:
    stale = B.stale_table(docs, info["tanggal"])
    truth = dict(info["nilai"])
    old = {j: v for key in {B._key(x) for x in truth} for j, v in B.leaves(stale.get(key), key).items()}
    changed = {j: v for j, v in truth.items() if j not in old or old[j] != v}
    text_truth = {j: x for j, x in truth.items() if not B.is_table_leaf(j)}
    out: dict = {}
    for v in sorted({v for j, v in changed.items() if v is not None and not B.is_table_leaf(j)}):
        paths = [j for j, x in text_truth.items() if x == v]
        kind = B._number_kind(paths[0])
        if any(B._number_kind(j) != kind for j in paths):
            continue
        new = B.new_value(v, kind, False)
        m, matched = B.mutate_text(text, v, new, kind, "konsisten")
        if matched:
            text = m
            out.update(dict.fromkeys(paths, str(new)))
    return text, out


class RagLLM:
    def __init__(self, model, provider, docs, texts, mutasi):
        self.llm = build_model(model, provider=provider)
        self.docs, self.texts, self.mutasi = docs, texts, mutasi

    def context(self) -> tuple[str, list[str]]:
        plan, phase = CURRENT["plan"], CURRENT["phase"]
        sources = plan.adapted_sources if phase.startswith("teradaptasi") else plan.stale_sources
        names = sorted(set(sources.values()), key=lambda n: self.docs[n]["tanggal"])
        parts = []
        for n in names:
            t = self.texts.get(n)
            if t is None:
                continue
            if phase == "teradaptasi_ubah" and n in plan.events and self.docs[n]["nilai"]:
                t = self.mutasi[n][0]
            parts.append(f"=== {n} (ditetapkan {self.docs[n]['tanggal'].isoformat()}) ===\n{t[:MAX_CHARS]}")
        if plan.case.get("tabel_teradaptasi") and phase.startswith("teradaptasi"):
            table = plan.adapted if phase == "teradaptasi_asli" else plan.adapted_ubah
            ter = {k: A._plain(table[k]) for k in ("ter_bulanan", "ter_harian") if k in table}
            parts.append(f"=== Lampiran tabel TER {', '.join(plan.events)} (transkripsi) ===\n"
                         + yaml.safe_dump(ter, allow_unicode=True, sort_keys=False))
        return "\n\n".join(parts), names

    def ask(self, question: str) -> AgentTurn:
        ctx, _ = self.context()
        for attempt in range(RETRIES):
            try:
                msg = self.llm.invoke([("system", SYSTEM + "\n\n" + ctx), ("human", question)])
                break
            except Exception:  # noqa: BLE001
                if attempt == RETRIES - 1:
                    raise
                time.sleep(20)
        usage = getattr(msg, "usage_metadata", None) or {}
        return AgentTurn(answer=str(msg.content), trace=[], rounds=1,
                         tokens_in=int(usage.get("input_tokens", 0) or 0),
                         tokens_out=int(usage.get("output_tokens", 0) or 0))


def main() -> int:
    ap = argparse.ArgumentParser(description='Stronger baseline for the walk-forward agent backtest: the same LLM with no tools, no rate table and no engine, but')
    ap.add_argument("--cases", required=True)
    ap.add_argument("--draft-backtest", required=True)
    ap.add_argument("--text-dataset", required=True)
    ap.add_argument("--phase", action="append", default=None)
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--provider", default="azure")
    ap.add_argument("--model", default=None)
    ap.add_argument("--output", required=True)
    ap.add_argument("--dry-run", action="store_true", help="only build and check the contexts, no LLM call")
    a = ap.parse_args()
    load_env()
    cases = A.load_cases(Path(a.cases))
    phases = tuple(a.phase) if a.phase else A.PHASES
    backtest_runs = json.loads(Path(a.draft_backtest).read_text(encoding="utf-8"))["run"]
    docs = B.documents(B.load_events(), B.load_labels())
    found, _ = B.source_texts(docs, Path(a.text_dataset))
    texts = B.phase2_texts(found, {n: t.text for n, t in found.items()}, True)

    json_mutasi = {r["dokumen"]: r.get("mutasi") or {} for r in backtest_runs if r["varian"] == "ubah"}
    mutasi, problems = {}, []
    for c in cases:
        for e in c["peristiwa"]:
            if e in texts and docs[e]["nilai"] and e not in mutasi:
                mutasi[e] = mutated_text(e, docs[e], texts[e], docs)
                want = {j: str(Decimal(v)) for j, v in json_mutasi.get(e, {}).items()}
                got = {j: str(Decimal(v)) for j, v in mutasi[e][1].items()}
                if want != got:
                    problems.append(f"{e}: mutasi berbeda dari draf ({got} vs {want})")
    missing = sorted({n for c in cases for n in c["peristiwa"] if n not in texts})
    print("teks tidak ada:", missing or "-")
    print("\n".join(problems) or "mutasi sama dengan draf backtest")

    real_phase_world = A.phase_world

    def phase_world(plan, phase):
        CURRENT.update(plan=plan, phase=phase)
        return real_phase_world(plan, phase)

    A.phase_world = phase_world
    rag = lambda: RagLLM(a.model, a.provider, docs, texts, mutasi)  # noqa: E731

    if a.dry_run:
        for c in cases:
            plan = A.plan_case(c, docs, backtest_runs)
            for p in phases:
                CURRENT.update(plan=plan, phase=p)
                ctx, names = RagLLM.context(type("X", (), {"docs": docs, "texts": texts, "mutasi": mutasi})())
                print(f"{c['id']:28} {p:17} {len(ctx):7d} char  {names}")
        return 0

    def report(r) -> None:
        print(f"{r.kasus} {r.fase:17} #{r.ulang} {r.hasil:22} {r.detik:6.1f}s", flush=True)

    h = A.run(cases, rag, ReadOnlyClient(), backtest_runs, phases, a.repeat, report)
    meta = {"provider": a.provider, "model": a.model or "default",
            "baseline": "LLM + teks peraturan yang berlaku (retrieval sempurna), tanpa tool/tabel/mesin",
            "sistem": SYSTEM, "maks_karakter_per_dokumen": MAX_CHARS, "masalah_mutasi": problems,
            "waktu": datetime.datetime.now().isoformat(timespec="seconds"), "ulang": a.repeat,
            "draf_backtest": a.draft_backtest, "kasus": a.cases}
    md, _ = A.write(h, meta, Path(a.output), "backtest_rag")
    print(md.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
