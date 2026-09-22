from __future__ import annotations

import json
import sys
from pathlib import Path

from ..environment import load_env
from ..taxes import get as tax_module

DEFAULT_YEAR = tax_module().default_year()

EXIT_FAILED = 3


def rule(title: str = "") -> None:
    print(("-- " + title + " ").ljust(72, "-") if title else "-" * 72)


def error(message: object) -> None:
    print(message, file=sys.stderr)


def show_result(result: dict) -> int:
    if not result.get("berhasil", True):
        error(f"GAGAL: {result.get('galat', '')}")
        if result.get("saran"):
            error(f"Saran: {result['saran']}")
        return 1

    if "pph_terutang" not in result:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    rule(result["jenis_perhitungan"])
    period = f" masa {result['masa_pajak']}" if result.get("masa_pajak") else ""
    print(f"Tahun pajak {result['tahun_pajak']}{period} | {result['metode_tarif']}")
    print()

    width = max((len(step["label"]) for step in result["langkah"]), default=20)
    for step in result["langkah"]:
        print(f"  {step['label']:<{width}}  {step['nilai_terbaca'] or '':>18}")
        if step["formula"]:
            print(f"  {'':<{width}}  = {step['formula']}")
        if step["catatan"]:
            print(f"  {'':<{width}}  ({step['catatan']})")
    print()
    rule()
    print(f"PPh 21 TERUTANG: {result['pph_terutang_terbaca']}")
    rule()

    for title, items, mark in (("Dasar hukum:", dict.fromkeys(result.get("dasar_hukum") or []), "-"),
                               ("Asumsi yang dipakai:", result.get("asumsi"), "-"),
                               ("PERINGATAN:", result.get("peringatan"), "!")):
        if items:
            print(f"\n{title}")
            for x in items:
                print(f"  {mark} {x}")
    print(f"\n{result.get('disclaimer', '')}")
    return 0


def llm_client(provider: str | None, model: str | None, cache: str | Path):
    load_env()
    from ..agent.runner import MissingApiKey
    from ..monitor.classify_llm import LLMCache
    from ..monitor.impact import MeteredClient, metered_langchain_call

    try:
        call, model_id = metered_langchain_call(provider, model)
    except (MissingApiKey, ImportError) as e:
        error(e)
        return None, None
    return MeteredClient(call, model_id, LLMCache(Path(cache))), model_id


def write_report(folder: str | Path, name: str, md: str, data: dict) -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.md").write_text(md, encoding="utf-8")
    (folder / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return folder / f"{name}.md"
