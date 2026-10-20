import yaml

from taxagent.evaluation import scorer
from taxagent.evaluation.scorer import DATA_DIR, reference_result, run_cases, scored_amount


def _natura_case():
    cases = yaml.safe_load((DATA_DIR / "kasus_agent_uji_resmi.yaml").read_text(encoding="utf-8"))["kasus"]
    return next(c for c in cases if c.get("tool") == "calculate_taxable_natura")


def test_scored_amount_prefers_pph_then_natura():
    assert scored_amount({"pph_terutang": 5, "natura_kena_pajak": 9}) == 5
    assert scored_amount({"natura_kena_pajak": 9}) == 9
    assert scored_amount({}) is None


def test_failed_natura_case_records_expected_amount(monkeypatch):
    monkeypatch.setattr(scorer.time, "sleep", lambda s: None)
    case = _natura_case()

    def broken():
        raise RuntimeError("api down")

    (h,) = run_cases([case], broken, retry_rounds=0)
    assert h.error and "api down" in h.error
    assert h.pph_harapan == str(reference_result(case)["natura_kena_pajak"])
