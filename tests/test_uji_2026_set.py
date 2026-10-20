from pathlib import Path

import yaml

from taxagent.agent.runner import names_other_tax
from taxagent.tools import call_tool

CASES = yaml.safe_load((Path(__file__).parents[1] / "taxagent" / "taxes" / "pph21" / "data" /
                        "kasus_agent_uji_2026.yaml").read_text(encoding="utf-8"))["kasus"]
KEYS = {"t26-01": 166250, "t26-02": 3600000, "t26-03": 1455000, "t26-04": 187500, "t26-05": 0, "t26-06": 0,
        "t26-07": 2500000, "t26-08": 5500000, "t26-09": 10000000}


def test_calculation_keys_and_year() -> None:
    calcs = [c for c in CASES if c["perilaku"] == "hitung"]
    assert {c["id"] for c in calcs} == set(KEYS)
    for c in calcs:
        assert c["argumen"]["tahun_pajak"] == 2026 and "2026" in c["pertanyaan"]
        assert int(call_tool(c["tool"], **c["argumen"])["pph_terutang"]) == KEYS[c["id"]], c["id"]


def test_refusals_and_scope_guard() -> None:
    refusals = {c["id"]: names_other_tax(c["pertanyaan"]) for c in CASES if c["perilaku"] == "tolak"}
    assert refusals == {"t26-10": True, "t26-11": True, "t26-12": True, "t26-13": True, "t26-14": False}
