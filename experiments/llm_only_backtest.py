from __future__ import annotations

import argparse
import datetime
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from taxagent.agent.runner import AgentTurn, build_model  # noqa: E402
from taxagent.environment import load_env  # noqa: E402
from taxagent.evaluation import agent_backtest as A  # noqa: E402
from taxagent.tools.regulation_graph import ReadOnlyClient  # noqa: E402

SYSTEM = ("Anda asisten Pajak Penghasilan Pasal 21 Indonesia. Jawab pertanyaan pengguna dengan menghitung PPh 21 "
          "sesuai ketentuan yang berlaku pada tahun pajak yang ditanyakan, dan tuliskan hasil akhirnya dalam rupiah.")
RETRIES = 3


class PlainLLM:
    def __init__(self, model: str | None, provider: str):
        self.llm = build_model(model, provider=provider)

    def ask(self, question: str) -> AgentTurn:
        for attempt in range(RETRIES):
            try:
                msg = self.llm.invoke([("system", SYSTEM), ("human", question)])
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
    ap = argparse.ArgumentParser(description='Baseline for the walk-forward agent backtest: the same LLM with no tools, no rate table and no graph answers the')
    ap.add_argument("--cases", required=True)
    ap.add_argument("--draft-backtest", required=True)
    ap.add_argument("--phase", action="append", default=None)
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--provider", default="azure")
    ap.add_argument("--model", default=None)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    load_env()
    cases = A.load_cases(Path(a.cases))
    phases = tuple(a.phase) if a.phase else A.PHASES
    backtest_runs = json.loads(Path(a.draft_backtest).read_text(encoding="utf-8"))["run"]

    def report(r) -> None:
        print(f"{r.kasus} {r.fase:17} #{r.ulang} {r.hasil:22} {r.detik:6.1f}s", flush=True)

    h = A.run(cases, lambda: PlainLLM(a.model, a.provider), ReadOnlyClient(), backtest_runs, phases, a.repeat, report)
    meta = {"provider": a.provider, "model": a.model or "default", "baseline": "LLM saja, tanpa tool/tabel/graf",
            "sistem": SYSTEM, "waktu": datetime.datetime.now().isoformat(timespec="seconds"), "ulang": a.repeat,
            "draf_backtest": a.draft_backtest, "kasus": a.cases}
    md, _ = A.write(h, meta, Path(a.output), "backtest_llm_saja")
    print(md.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
