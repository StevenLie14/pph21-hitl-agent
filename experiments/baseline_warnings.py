from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path

WARNING = re.compile(
    r"tidak (dapat|bisa) (di)?pastikan|tidak (dapat|bisa) memastikan|belum (dapat|bisa) dipastikan"
    r"|teks(nya)? (yang (di)?(berikan|sediakan|tersedia) )?(tidak|belum) (memuat|mencakup|cukup|mengatur)"
    r"|tidak (memuat|mencakup) (aturan|ketentuan|perubahan)|belum cukup|tidak tersedia dalam teks"
    r"|bukan angka .{0,40}dapat dipastikan|mungkin (sudah )?(berubah|diperbarui)"
    r"|perlu (dicek|diperiksa|dikonfirmasi|diverifikasi)|verifikasi|belum terverifikasi|tidak dapat diverifikasi"
    r"|tidak (ada|terdapat) dalam (teks|peraturan)",
    re.I,
)
PHASES = ("basi_hilang", "basi_lanjutan", "sadar", "teradaptasi_asli", "teradaptasi_ubah")
RESULT_FILES = ("result.json", "backtest_rag.json", "backtest_llm_saja.json")


def load_runs(directory: Path):
    for set_dir in sorted(p for p in directory.iterdir() if p.is_dir() and p.name.startswith("set")):
        path = next((set_dir / f for f in RESULT_FILES if (set_dir / f).exists()), None)
        if path is None:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        partial = {c["kasus"] for c in data["kasus"] if c.get("sebagian")}
        for run in data["run"]:
            if run["kasus"] not in partial:
                yield set_dir.name, run


def snippet(text: str, match: re.Match, width: int = 160) -> str:
    start, end = max(0, match.start() - width), min(len(text), match.end() + width)
    body = text[start:match.start()] + "**" + match.group(0) + "**" + text[match.end():end]
    return ("…" if start else "") + " ".join(body.split()) + ("…" if end < len(text) else "")


def main() -> None:
    parser = argparse.ArgumentParser(description='Count written warnings in the tool-free backtest baselines (LLM alone, LLM with texts).')
    parser.add_argument("dirs", nargs="+", type=Path, help="baseline result directories (each with set1, set2)")
    parser.add_argument("--review", type=Path, help="write every matched answer to this Markdown file")
    args = parser.parse_args()

    review = []
    for directory in args.dirs:
        counts = collections.Counter()
        totals = collections.Counter()
        for set_name, run in load_runs(directory):
            answer = run.get("jawaban") or ""
            match = WARNING.search(answer)
            totals[run["fase"]] += 1
            if match:
                counts[run["fase"]] += 1
                review.append((directory.name, set_name, run, match, answer))
        print(f"== {directory}")
        for phase in PHASES:
            if totals[phase]:
                print(f"  {phase:18s} warned {counts[phase]:3d} / {totals[phase]}")

    if args.review:
        lines = ["# Written warnings found in baseline answers", "",
                 "Mark each row: W = a real warning about stale or missing data, N = not a warning.", ""]
        for i, (name, set_name, run, match, answer) in enumerate(review, 1):
            lines.append(f"{i}. [ ] `{name}/{set_name}` {run['kasus']} {run['fase']} #{run['ulang']} "
                         f"(result: {run['hasil']})  ")
            lines.append(f"   {snippet(answer, match)}")
        args.review.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"review: {len(review)} answers -> {args.review}")


if __name__ == "__main__":
    main()
