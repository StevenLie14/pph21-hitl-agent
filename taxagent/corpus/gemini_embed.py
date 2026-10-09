from __future__ import annotations

import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor

from ..settings import get_settings

log = logging.getLogger(__name__)

MODEL = "gemini-embedding-2"
DIM = get_settings().gemini_embed_dim
QUERY_PREFIX = "task: search result | query: "
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:embedContent"
TIMEOUT_S = 4.0
FAILURE_BACKOFF_S = 60.0
_cache: dict[str, list[float]] = {}
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="gemini-embed")
_failed_until = 0.0


def _api_key() -> str | None:
    if not get_settings().google_api_key:
        from ..environment import load_env

        load_env()
    return get_settings().google_api_key


def truncate(v: list[float], dim: int = DIM) -> list[float]:
    x = v[:dim]
    n = math.sqrt(sum(a * a for a in x)) or 1.0
    return [a / n for a in x]


def query_vector(text: str) -> list[float] | None:
    text = " ".join((text or "").split())
    if not text:
        return None
    if text in _cache:
        return _cache[text]
    global _failed_until
    api_key = _api_key()
    if not api_key or time.monotonic() < _failed_until:
        return None

    def call() -> list[float]:
        import httpx

        r = httpx.post(URL, headers={"x-goog-api-key": api_key}, timeout=TIMEOUT_S,
                       json={"model": f"models/{MODEL}", "content": {"parts": [{"text": QUERY_PREFIX + text}]}})
        r.raise_for_status()
        return truncate(r.json()["embedding"]["values"])

    try:
        v = _executor.submit(call).result(timeout=TIMEOUT_S)
    except Exception:  # noqa: BLE001
        log.warning("Gemini query embedding failed; BM25 only for %.0f s", FAILURE_BACKOFF_S, exc_info=True)
        _failed_until = time.monotonic() + FAILURE_BACKOFF_S
        return None
    if len(_cache) > 1000:
        _cache.clear()
    _cache[text] = v
    return v
