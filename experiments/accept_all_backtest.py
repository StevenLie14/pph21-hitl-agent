import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import taxagent.update.backtest as bt  # noqa: E402

_orig = bt.assemble_draft


def accept_all(*args, **kwargs):
    d = _orig(*args, **kwargs)
    if d.decision == "tahan":
        d.decision_reason = ["(accepted unread) " + "; ".join(d.decision_reason)]
        d.decision = "siap"
    return d


def main() -> int:
    ap = argparse.ArgumentParser(description='Cumulative replay without an approver where every held draft is accepted unread.')
    ap.add_argument("--text-dataset", required=True, help="pajak_details.json built by pipeline/corpus_pajak.py")
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    bt.assemble_draft = accept_all
    from taxagent.cli import main as cli

    return cli(["draft-backtest", "--text-dataset", a.text_dataset, "--llm", "--cumulative", "--phase1-llm",
                "--lampiran-tables", "--output", a.output])


if __name__ == "__main__":
    sys.exit(main())
