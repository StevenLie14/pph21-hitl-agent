import http.client

import pytest

from taxagent.monitor import sources as sumber


def test_incomplete_read_retried_then_source_failure(monkeypatch):
    panggil = []

    def putus(req, timeout):
        panggil.append(1)
        raise http.client.IncompleteRead(b"x" * 10, 5)

    monkeypatch.setattr(sumber.urllib.request, "urlopen", putus)
    monkeypatch.setattr(sumber.time, "sleep", lambda s: None)
    with pytest.raises(sumber.SourceError):
        sumber.fetch("https://contoh.test/a.pdf", retries=3)
    assert len(panggil) == 3
