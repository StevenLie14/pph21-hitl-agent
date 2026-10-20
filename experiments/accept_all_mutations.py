import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import taxagent.update.evaluation as ev  # noqa: E402

_orig_assemble = ev.assemble_draft
_orig_score = ev._score_case


def accept_all(*args, **kwargs):
    d = _orig_assemble(*args, **kwargs)
    d._asli = d.decision
    if d.decision == "tahan":
        d.decision = "siap"
    return d


def score(c, d, expected_base, llm=None):
    _orig_score(c, d, expected_base, llm)
    c.asli_keputusan = getattr(d, "_asli", d.decision)
    c.masuk = sorted({p.key for p in d.berubah}) if d.decision == "siap" else []


def main() -> int:
    ap = argparse.ArgumentParser(description='Mutation test where every held draft is accepted unread.')
    ap.add_argument("--text-dataset", required=True, help="pajak_details.json built by pipeline/corpus_pajak.py")
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    ev.assemble_draft = accept_all
    ev._score_case = score
    from taxagent.cli import main as cli

    return cli(["draft-evaluate", "--text-dataset", a.text_dataset, "--llm", "--lampiran-tables", "--parallel", "1",
                "--output", a.output])


if __name__ == "__main__":
    sys.exit(main())
