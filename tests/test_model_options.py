import pytest

from taxagent.agent.runner import _sampling_options, supports_temperature


@pytest.fixture(autouse=True)
def bersih(monkeypatch):
    monkeypatch.delenv("LLM_TANPA_TEMPERATURE", raising=False)
    monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)


@pytest.mark.parametrize("nama,dukung", [
    ("gpt-4.1-mini", True), ("gemini-2.5-flash", True), (None, True),
    ("gpt-6-luna", False), ("GPT-5-mini", False), ("o4-mini", False), ("o3", False),
])
def test_supports_temperature(nama, dukung):
    assert supports_temperature(nama) is dukung


def test_regular_and_reasoning_model_options(monkeypatch):
    assert _sampling_options("gpt-4.1-mini", 0.0) == {"temperature": 0.0}
    assert _sampling_options("gpt-6-luna", 0.0) == {"reasoning_effort": "none"}
    monkeypatch.setenv("LLM_REASONING_EFFORT", "low")
    assert _sampling_options("gpt-6-luna", 0.0) == {"reasoning_effort": "low"}


def test_force_via_environment(monkeypatch):
    monkeypatch.setenv("LLM_TANPA_TEMPERATURE", "1")
    assert supports_temperature("deployment-ku") is False
    monkeypatch.setenv("LLM_TANPA_TEMPERATURE", "0")
    assert supports_temperature("gpt-6-luna") is True
