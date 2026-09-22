from __future__ import annotations

from pathlib import Path

import pytest

from taxagent.settings import get_settings


@pytest.mark.parametrize("nilai,harap", [("0", False), (" 0 ", False), ("false", False), ("off", False),
                                         ("1", True), ("ya", True), ("", True)])
def test_feature_flags(monkeypatch, nilai, harap):
    monkeypatch.setenv("PPH21_TOOL_GRAF", nilai)
    s = get_settings()
    assert s.graph_tools is harap


def test_empty_values_fall_back_to_defaults(monkeypatch):
    for k in ("OPENAI_MODEL", "PPH21_PERMINTAAN_AGENT", "AZURE_OPENAI_API_VERSION"):
        monkeypatch.setenv(k, "")
    s = get_settings()
    assert s.openai_model == "gpt-4o"
    assert s.stale_reports_file == Path("monitor_state/permintaan_agent.jsonl")
    assert s.azure_api_version == "2024-10-21"


def test_settings_are_read_at_call_time(monkeypatch):
    monkeypatch.setenv("PPH21_PERMINTAAN_AGENT", "x/y.jsonl")
    assert get_settings().stale_reports_file == Path("x/y.jsonl")


def test_secrets_are_hidden(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "rahasia-123")
    monkeypatch.setenv("NEO4J_V2_PASSWORD", "sandi-456")
    s = get_settings()
    assert s.google_api_key == "rahasia-123" and s.neo4j_v2_password == "sandi-456"
    assert "rahasia-123" not in repr(s) and "sandi-456" not in repr(s)


def test_model_name_per_provider(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "dep-x")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    s = get_settings()
    assert s.model_name("azure") == "dep-x" and s.model_name("openai") == "gpt-4o" and s.model_name("lain") is None


def test_gemini_is_not_an_llm_provider(monkeypatch):
    import pytest

    from taxagent.agent import MissingApiKey, UnsupportedProvider, build_model
    from taxagent.agent.runner import default_provider

    with pytest.raises(UnsupportedProvider):
        build_model(provider="gemini")
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    with pytest.raises(UnsupportedProvider):
        default_provider()
    monkeypatch.delenv("LLM_PROVIDER")
    for k in ("AZURE_OPENAI_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.setenv(k, "")
    monkeypatch.setenv("GOOGLE_API_KEY", "embed-only")
    with pytest.raises(MissingApiKey):
        default_provider()
