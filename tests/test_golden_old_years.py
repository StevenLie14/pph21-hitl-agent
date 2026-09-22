from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from taxagent.evaluation import agent_backtest as A
from taxagent.taxes.pph21 import tools as T
from taxagent.update.backtest import documents, load_events, load_labels

FIXTURE = Path(__file__).parent / "fixtures" / "contoh_resmi_lama.yaml"
CASES = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))["contoh"]


@pytest.fixture(scope="module")
def plans() -> dict:
    docs = documents(load_events(None), load_labels())
    by_id = {c["id"]: c for c in A.load_cases(None)}
    return {k: A.plan_case(by_id[k], docs, []) for k in {c["kasus"] for c in CASES}}


@pytest.mark.parametrize("case", CASES, ids=[f"{c['kasus']}::{c['nama']}" for c in CASES])
def test_old_year_official_example(case: dict, plans: dict) -> None:
    plan = plans[case["kasus"]]
    year = plan.case["tahun"]
    table = A._table(plan.adapted, year, list(plan.events), plan.adapted_sources)
    with A.world({year: table}, plan.adapted_cut):
        result = T.calculate_pph21_permanent_annual(tahun_pajak=year, nilai_per_bulan=True, **case["argumen"])
    assert str(result["pph_terutang"]) == str(case["harapan"]), case["sumber"]


def test_every_old_case_cites_source_and_flags_deviations() -> None:
    for case in CASES:
        assert case.get("sumber") and case.get("berkas"), case["nama"]
        if "angka_resmi" in case:
            assert case.get("contoh_resmi_keliru"), f"{case['nama']}: deviation from the printed amount needs a reason"
