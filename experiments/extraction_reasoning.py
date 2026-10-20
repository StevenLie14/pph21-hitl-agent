from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, ".")
from taxagent.environment import load_env  # noqa: E402

load_env()
from taxagent.cli._common import llm_client  # noqa: E402
from taxagent.corpus.text_source import CorpusIndex, jdih_first  # noqa: E402
from taxagent.settings import get_settings  # noqa: E402
from taxagent.update.body_tables import reflow_source  # noqa: E402
from taxagent.update.evaluation import (  # noqa: E402
    _key,
    _llm_wrong,
    _number_kind,
    base_with,
    is_table_leaf,
    load_labels,
    mutate_text,
    new_value,
    texts_from_dataset,
)
from taxagent.update.llm import extract_llm, groups_in_text, reread_changed  # noqa: E402

EXCLUDED = {"PER-16/PJ/2016", "PP 58 Tahun 2023", "PER-31/PJ/2009", "PER-32/PJ/2015"}


def labelled_wrong(reading, label: dict) -> bool:
    return any(j in label and label[j] is not None and v is not None and Decimal(str(v)) != Decimal(str(label[j]))
               for j, v in reading.values.items())


def digit_cases(doc: str, info: dict, text: str, client) -> list[dict]:
    label = info["nilai"]
    groups = groups_in_text(text)
    original = extract_llm(text, client, groups)
    out = [{"dokumen": doc, "jenis": "asli", "llm_salah": _llm_wrong(original, base_with(label)),
            "llm_salah_berlabel": labelled_wrong(original, label)}]
    text_label = {j: x for j, x in label.items() if not is_table_leaf(j)}
    for v in sorted({v for v in text_label.values() if v is not None}):
        paths = [j for j, x in text_label.items() if x == v]
        kind = _number_kind(paths[0])
        if any(_number_kind(j) != kind for j in paths):
            continue
        new = new_value(v, kind, False)
        case = {"dokumen": doc, "jenis": "digit", "angka": f"{','.join(paths)}: {v} -> {new}"}
        if new is None:
            out.append({**case, "keputusan": "dilewati"})
            continue
        mutated, matched = mutate_text(text, v, new, kind, "digit")
        if matched == 0:
            out.append({**case, "keputusan": "dilewati"})
            continue
        keys = {_key(j) for j in paths}
        reading = reread_changed(original, mutated, client, groups, keys)
        out.append({**case, "llm_salah": _llm_wrong(reading, base_with(label)),
                    "llm_salah_berlabel": labelled_wrong(reading, label), "llm_valid": reading.valid,
                    "bacaan": {j: str(x) for j, x in reading.values.items() if j in paths}})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text-dataset", default="../application/output/dataset/aturan_pajak/pajak_details.json")
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--parallel", type=int, default=4)
    a = ap.parse_args()

    labels = load_labels()
    texts, sources = jdih_first(list(labels), texts_from_dataset(labels, Path(a.text_dataset)))
    corpus = CorpusIndex()
    for i, t in list(texts.items()):
        src = corpus.pick(i)
        if src is not None and src.text == t:
            texts[i] = reflow_source(src).text
    client, model_id = llm_client(None, None, a.cache)
    if client is None:
        return 3
    docs = [i for i in labels if i in texts]
    with ThreadPoolExecutor(max_workers=a.parallel) as ex:
        cases = [c for r in ex.map(lambda i: digit_cases(i, labels[i], texts[i], client), docs) for c in r]
    digit = [c for c in cases if c["jenis"] == "digit" and "llm_salah" in c]
    orig = [c for c in cases if c["jenis"] == "asli"]
    old = [c for c in digit if c["dokumen"] not in EXCLUDED]
    summary = {
        "model": model_id, "reasoning_effort": get_settings().llm_reasoning_effort, "dokumen": len(docs),
        "lama_27dok_digit_salah": sum(c["llm_salah"] for c in old), "lama_27dok_digit_n": len(old),
        "berlabel_digit_salah": sum(c["llm_salah_berlabel"] for c in digit), "berlabel_digit_n": len(digit),
        "berlabel_asli_salah": sum(c["llm_salah_berlabel"] for c in orig), "asli_n": len(orig),
        "berlabel_digit_salah_27dok": sum(c["llm_salah_berlabel"] for c in old),
        "digit_tidak_valid": sum(not c.get("llm_valid", True) for c in digit),
    }
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    name = f"ekstraksi_digit_{summary['reasoning_effort']}.json"
    (out / name).write_text(json.dumps({"ringkasan": summary, "sumber_teks": sources, "kasus": cases},
                                       ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
