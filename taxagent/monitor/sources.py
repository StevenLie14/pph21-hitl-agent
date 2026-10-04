from __future__ import annotations

import hashlib
import http.client
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from ..settings import get_settings
from .identity import RegulationId, from_slug

URL_FEED = "https://jdih.kemenkeu.go.id/feed.json"
_RE_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class SourceError(RuntimeError):
    pass


@dataclass(frozen=True)
class FeedDocument:
    id: str
    url: str
    slug: str
    title: str
    subject: str
    date: str
    identity: RegulationId | None

    @property
    def artikel(self) -> bool:
        return bool(_RE_UUID.match(self.slug))


def user_agent() -> str:
    contact = get_settings().monitor_contact
    return "pph21-pantau/0.1 (riset tesis PPh 21" + (f"; {contact}" if contact else "") + ")"


MIN_DELAY = 2.0
_last_request = [0.0]


def fetch(url: str, timeout: float = 60.0, retries: int = 3, delay: float = 2.0) -> bytes:
    error: Exception | None = None
    for i in range(retries):
        wait = MIN_DELAY - (time.monotonic() - _last_request[0])
        if wait > 0:
            time.sleep(wait)
        _last_request[0] = time.monotonic()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": user_agent()})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
            error = exc
            if i + 1 < retries:
                time.sleep(delay * (2 ** i))
    raise SourceError(f"gagal mengambil {url}: {error}")


def fetch_cached(fetch, folder: Path):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)

    def _fetch(url: str) -> bytes:
        cache_file = folder / hashlib.sha1(url.encode()).hexdigest()
        if cache_file.exists():
            return cache_file.read_bytes()
        content = fetch(url)
        cache_file.write_bytes(content)
        return content

    return _fetch


def parse_feed(raw: bytes | str) -> list[FeedDocument]:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SourceError(f"feed bukan JSON yang valid: {exc}") from exc
    if not isinstance(data, dict) or "jsonfeed.org" not in str(data.get("version", "")):
        raise SourceError("format feed tidak dikenal (bukan JSON Feed)")
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise SourceError("feed tidak berisi item")

    documents: list[FeedDocument] = []
    for it in items:
        if not isinstance(it, dict) or not it.get("id"):
            raise SourceError(f"item feed tanpa id: {it!r}"[:200])
        url = str(it.get("url") or it["id"])
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        title = re.sub(r"\s+", " ", str(it.get("title", ""))).strip()
        subject = re.sub(r"\s+", " ", str(it.get("content_html", ""))).strip()
        documents.append(
            FeedDocument(
                id=str(it["id"]),
                url=url,
                slug=slug,
                title=title,
                subject=subject,
                date=str(it.get("date_modified", ""))[:10],
                identity=from_slug(slug),
            )
        )
    return documents


def fetch_feed(url: str = URL_FEED) -> list[FeedDocument]:
    return parse_feed(fetch(url))
