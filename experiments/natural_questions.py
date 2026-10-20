from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urldefrag

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from taxagent.paths import DATA  # noqa: E402

CASES = Path(__file__).resolve().parents[1] / "taxagent" / "taxes" / "pph21" / "data" / "kasus_agent_uji_alami.yaml"
OUT = DATA / "uji_alami_asli.yaml"
HEADERS = {"User-Agent": "Mozilla/5.0 (academic research; tax QA evaluation)"}


def pages_needed(cases: list[dict]) -> dict[str, dict[str, str]]:
    by_page: dict[str, dict[str, str]] = defaultdict(dict)
    for case in cases:
        page, anchor = urldefrag(case["sumber"])
        by_page[page][anchor] = case["id"]
    return dict(by_page)


_SELF_INTRO = re.compile(r"\b((?i:(?:perkenalkan|kenalkan)\s+(?:nama\s+)?saya|nama\s+saya))\s+(?:[A-Z][\w'.-]*\s*){1,5}")


def redact_names(text: str) -> str:
    return _SELF_INTRO.sub(lambda m: f"{m.group(1)} [nama] ", text).replace(" [nama] ,", " [nama],")


def extract(html: str, anchors: dict[str, str]) -> dict[str, dict]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    found = {}
    for anchor, case_id in anchors.items():
        node = soup.find(id=anchor)
        text = node.find(class_="wpd-comment-text") if node else None
        if text is None:
            continue
        cut = text.find(class_="wpdiscuz-readmore") is not None
        for marker in text.find_all(class_=["wpdiscuz-hellip", "wpdiscuz-readmore"]):
            marker.decompose()
        date = node.find(class_="wpd-comment-date")
        found[case_id] = {"pertanyaan": redact_names(" ".join(text.get_text(" ", strip=True).split())),
                          "tanggal": date.get_text(strip=True) if date else None, "terpotong": cut}
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description='Original wording of the natural-question test set (taxagent/taxes/pph21/data/kasus_agent_uji_alami.yaml).')
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--delay", type=float, default=4.0, help="seconds between page requests")
    args = parser.parse_args()

    cases = yaml.safe_load(CASES.read_text(encoding="utf-8"))["kasus"]
    pages = pages_needed(cases)
    if args.dry_run:
        for page, anchors in pages.items():
            print(page, sorted(anchors.values()))
        return 0

    import requests

    out: dict[str, dict] = {}
    for i, (page, anchors) in enumerate(pages.items()):
        if i:
            time.sleep(args.delay)
        response = requests.get(page, headers=HEADERS, timeout=60)
        response.raise_for_status()
        for case_id, item in extract(response.text, anchors).items():
            out[case_id] = {"url": next(c["sumber"] for c in cases if c["id"] == case_id), **item}
    missing = sorted({c["id"] for c in cases} - set(out))
    OUT.write_text(
        "# Original question text of kasus_agent_uji_alami.yaml, research use only; NOT for redistribution.\n"
        f"# Source: tanyapajak.flazztax.com, fetched {dt.date.today().isoformat()}. No asker names, no site answers.\n"
        + yaml.safe_dump({"kasus": dict(sorted(out.items()))}, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8")
    print(f"{len(out)} pertanyaan ditulis ke {OUT}; tidak ditemukan: {missing or '-'}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
