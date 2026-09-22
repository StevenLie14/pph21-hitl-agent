from __future__ import annotations

import pytest

pytest.importorskip("dotenv")

from taxagent import environment as lingkungan  # noqa: E402


def test_load_neo4j_env_only_neo4j_variables_and_no_override(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("NEO4J_URI=bolt://contoh:7687\nNEO4J_USER=baru\nAZURE_OPENAI_API_KEY=rahasia\n",
                                   encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(lingkungan, "REPO_ROOT", tmp_path / "tidak_ada")
    monkeypatch.delenv("NEO4J_URI", raising=False)
    monkeypatch.setenv("NEO4J_USER", "lama")
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)

    lingkungan.load_neo4j_env()

    import os

    assert os.environ["NEO4J_URI"] == "bolt://contoh:7687"
    assert os.environ["NEO4J_USER"] == "lama"
    assert "AZURE_OPENAI_API_KEY" not in os.environ
