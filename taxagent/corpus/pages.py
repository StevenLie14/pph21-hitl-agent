from __future__ import annotations

from pathlib import Path


def _starts(pages: list[str]) -> list[int]:
    starts, pos = [], 0
    for h in pages:
        starts.append(pos)
        pos += len(h) + 1
    return starts


def page_starts(corpus_dir: Path, id_: str, text: str) -> list[int] | None:
    folder = corpus_dir / "ocr" / id_
    if folder.is_dir():
        pages = [f.read_text(encoding="utf-8") for f in sorted(folder.glob("[0-9]*.txt"))]
        if pages and "\n".join(pages) == text:
            return _starts(pages)
    pdf = corpus_dir / "pdf" / f"{id_}.pdf"
    if pdf.exists():
        try:
            import pymupdf
        except ImportError:
            return None
        with pymupdf.open(pdf) as doc:
            pages = [p.get_text() for p in doc]
        if "\n".join(pages) == text:
            return _starts(pages)
    return None


def page_link(url: str | None, page: int | None) -> str | None:
    if not url:
        return None
    return f"{url}#page={page}" if page and url.lower().split("?")[0].endswith(".pdf") else url
