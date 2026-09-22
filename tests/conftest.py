import pytest


@pytest.fixture(autouse=True)
def _tanpa_gemini(monkeypatch):
    monkeypatch.setattr("taxagent.corpus.gemini_embed.query_vector", lambda teks: None)
