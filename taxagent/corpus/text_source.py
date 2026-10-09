from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..monitor.identity import canon_id
from ..paths import DATA

CORPUS_INDEX = DATA / "korpus_gabung" / "indeks.jsonl"
JDIH_FILES = DATA / "korpus_jdih" / "berkas"
JDIH_PDFS = DATA / "korpus_jdih" / "pdf"
MIN_TEXT = 1000


@dataclass
class SourceText:
    text: str
    source: str
    quality: str | None
    jdih_id: str | None = None

    @property
    def label(self) -> str:
        return self.source + (f" ({self.quality})" if self.quality and self.quality != "andal" else "")

    def pdf(self, pdf_dir: Path = JDIH_PDFS) -> Path | None:
        if not self.jdih_id:
            return None
        p = Path(pdf_dir) / f"{self.jdih_id}.pdf"
        return p if p.exists() else None

    def pdf_url(self, files_dir: Path = JDIH_FILES) -> str | None:
        if not self.jdih_id:
            return None
        meta = Path(files_dir) / f"{self.jdih_id}.json"
        if not meta.exists():
            return None
        return json.loads(meta.read_text(encoding="utf-8")).get("url")


def _canon(name: str | None) -> str | None:
    ident = canon_id(name or "")
    return str(ident) if ident is not None else None


class CorpusIndex:
    def __init__(self, path: Path = CORPUS_INDEX):
        self.by_key: dict[str, list[dict]] = {}
        path = Path(path)
        if not path.exists():
            return
        with path.open(encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                key = _canon(r.get("kunci"))
                if key and r.get("teks") and r.get("mutu") != "tidak_terpakai":
                    self.by_key.setdefault(key, []).append(r)

    def _text(self, entries: list[dict], source: str, quality: set[str]) -> SourceText | None:
        best = None
        for r in entries:
            if r.get("sumber") != source or (r.get("mutu") or "perlu_dicek") not in quality:
                continue
            p = Path(r["teks"])
            if not p.exists():
                continue
            t = p.read_text(encoding="utf-8")
            if len(t) >= MIN_TEXT and (best is None or len(t) > len(best.text)):
                best = SourceText(t, "jdih" if source == "jdih" else "pajak.go.id", r.get("mutu") or "perlu_dicek",
                                  r.get("id") if source == "jdih" else None)
        return best

    def pick(self, name: str, dataset_text: str | None = None) -> SourceText | None:
        entries = self.by_key.get(_canon(name) or "", [])
        found = self._text(entries, "jdih", {"andal"}) or self._text(entries, "pajak", {"andal", "perlu_dicek"})
        if found is None and dataset_text and len(dataset_text) >= MIN_TEXT:
            found = SourceText(dataset_text, "pajak.go.id", None)
        return found or self._text(entries, "jdih", {"perlu_dicek"})


def jdih_first(names: list[str], dataset_texts: dict[str, str], corpus: CorpusIndex | None = None
               ) -> tuple[dict[str, str], dict[str, str]]:
    corpus = corpus if corpus is not None else CorpusIndex()
    text, source = {}, {}
    for n in names:
        t = corpus.pick(n, dataset_texts.get(n))
        if t is None and dataset_texts.get(n):
            t = SourceText(dataset_texts[n], "pajak.go.id", None)
        if t is not None:
            text[n], source[n] = t.text, t.label
    return text, source
