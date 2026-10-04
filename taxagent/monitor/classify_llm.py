from __future__ import annotations

import contextlib
import hashlib
import json
import re
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from ..settings import get_settings

PROMPT_VERSION = "v1-2026-10-06"
LLM_CATEGORIES = ("dasar", "fasilitas", "prosedural", "tidak_relevan")

SYSTEM_PROMPT = """\
Anda membantu pemelihara kalkulator PPh Pasal 21 (pajak penghasilan atas penghasilan \
sehubungan dengan pekerjaan, jasa, atau kegiatan orang pribadi) di Indonesia. Untuk setiap \
peraturan yang baru terbit, tentukan apakah pemelihara perlu meninjaunya. Anda hanya melihat \
jenis dan nomor, judul, dan perihal peraturan; teks lengkapnya tidak tersedia.

Kategori:
- dasar: mengubah angka atau mekanisme hitung PPh Pasal 21/26, termasuk pengurang (misalnya \
zakat, iuran pensiun), natura/kenikmatan, dan pemberi kerja atau penerima penghasilan dengan \
kriteria tertentu.
- fasilitas: PPh Pasal 21 ditanggung pemerintah, dibebaskan, atau dikenai tarif 0%.
- prosedural: prosedur KHUSUS PPh Pasal 21/26, misalnya bukti pemotongan atau SPT Masa PPh \
Pasal 21/26.
- tidak_relevan: lainnya, termasuk prosedur umum perpajakan yang berlaku untuk semua jenis \
pajak, pajak lain, PPh selain Pasal 21/26, dan peraturan di luar perpajakan.

Melewatkan peraturan yang berdampak jauh lebih mahal daripada meninjau satu peraturan yang \
ternyata tidak relevan. Jika judul atau perihal memberi alasan yang wajar bahwa isinya dapat \
mengubah perhitungan, fasilitas, atau prosedur PPh Pasal 21/26, pilih kategori positif yang \
paling mungkin.

Jawab HANYA dengan JSON: {"kategori": "dasar|fasilitas|prosedural|tidak_relevan", \
"alasan": "satu kalimat"}"""

TEXT_PROMPT_VERSION = "teks-v1-2026-10-06"
_TITLE_INPUT = "Anda hanya melihat jenis dan nomor, judul, dan perihal peraturan; teks lengkapnya tidak tersedia."
assert _TITLE_INPUT in SYSTEM_PROMPT
TEXT_SYSTEM_PROMPT = SYSTEM_PROMPT.replace(
    _TITLE_INPUT,
    "Anda melihat jenis dan nomor, judul, dan CUPLIKAN teks peraturan: bagian awal dokumen, lalu "
    "potongan di sekitar setiap penyebutan Pasal 21 atau Pasal 26 (bila ada), dipisahkan \"[...]\". "
    "Putuskan berdasarkan isi teks, bukan hanya judul. Menyebut Pasal 21 tidak otomatis relevan: "
    "perhatikan apakah peraturan mengatur PPh Pasal 21/26 itu sendiri atau hanya menyebutnya di antara "
    "jenis pajak lain dalam prosedur umum.",
)

KEYWORD_TEXT_PROMPT_VERSION = "teks-v2-kata-kunci-2026-10-19"
KEYWORD_TEXT_SYSTEM_PROMPT = SYSTEM_PROMPT.replace(
    _TITLE_INPUT,
    "Anda melihat jenis dan nomor, judul, dan CUPLIKAN teks peraturan: bagian awal dokumen, lalu "
    "potongan di sekitar penyebutan Pasal 21 atau Pasal 26 dan istilah parameter PPh Pasal 21 (misalnya "
    "penghasilan tidak kena pajak, biaya jabatan, tarif Pasal 17, natura, tarif efektif), dipisahkan \"[...]\". "
    "Putuskan berdasarkan isi teks, bukan hanya judul. Menyebut Pasal 21 atau istilah itu tidak otomatis "
    "relevan: perhatikan apakah peraturan mengatur PPh Pasal 21/26 itu sendiri atau hanya menyebutnya di antara "
    "jenis pajak lain dalam prosedur umum.",
)

TOOLS_PROMPT_VERSION = "alat-v1-2026-10-20"
TOOLS_MAX_STEPS = 6
_ANSWER_START = "Jawab HANYA dengan JSON:"
assert _ANSWER_START in SYSTEM_PROMPT
TOOLS_SYSTEM_PROMPT = SYSTEM_PROMPT.split(_ANSWER_START)[0].replace(
    _TITLE_INPUT,
    "Anda melihat jenis dan nomor, judul, dan perihal peraturan; teks lengkapnya TIDAK diberikan, tetapi dapat "
    "Anda telusuri dengan alat di bawah. Putuskan berdasarkan isi teks, bukan hanya judul. Menyebut Pasal 21 tidak "
    "otomatis relevan: perhatikan apakah peraturan mengatur PPh Pasal 21/26 itu sendiri atau hanya menyebutnya di "
    "antara jenis pajak lain dalam prosedur umum.",
) + f"""Alat (satu per langkah, paling banyak {TOOLS_MAX_STEPS} langkah):
- {{"aksi": "cari", "kueri": "kata atau frasa"}}: posisi kemunculan di teks dan potongan pendek di sekitarnya;
- {{"aksi": "baca", "posisi": 12345}}: 1.500 karakter teks mulai dari posisi itu;
- {{"aksi": "selesai", "kategori": "dasar|fasilitas|prosedural|tidak_relevan", "alasan": "satu kalimat"}}: jawaban akhir.
Saran: cari "Pasal 21", "Pasal 26", istilah parameter (misalnya "penghasilan tidak kena pajak", "biaya jabatan", \
"tarif", "natura", "ditanggung pemerintah", "bukti pemotongan"), lalu baca bagian yang menjanjikan.

Setiap langkah jawab HANYA satu JSON."""

LLMCall = Callable[[str, str], str]

_RE_ARTICLE_21_26 = re.compile(r"PASAL\s*2[16]\b", re.I)


def excerpt(text: str, limit: int = 6000, head: int = 1500, window: int = 500) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    if len(t) <= limit:
        return t
    spans = [(0, head)]
    for m in _RE_ARTICLE_21_26.finditer(t, head):
        a, b = max(head, m.start() - window), min(len(t), m.end() + window)
        if a <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], b))
        else:
            spans.append((a, b))
    if len(spans) == 1:
        return t[:limit]
    result, budget = [], limit
    for a, b in spans:
        piece = t[a:min(b, a + budget)]
        result.append(piece)
        budget -= len(piece)
        if budget <= 0:
            break
    return " [...] ".join(result)


def round_robin_spans(t: str, per_group: list[list[int]], limit: int, head: int, window: int) -> str:
    spans, budget, round_no = [(0, head)], limit - head, 0
    while budget > 0 and any(round_no < len(p) for p in per_group):
        for positions in per_group:
            if round_no >= len(positions) or budget <= 0:
                continue
            a, b = max(head, positions[round_no] - window), min(len(t), positions[round_no] + window)
            if any(a < y and x < b for x, y in spans):
                continue
            b = min(b, a + budget)
            spans.append((a, b))
            budget -= b - a
        round_no += 1
    return " [...] ".join(t[a:b] for a, b in sorted(spans))


def manifest_terms(skill: str = "pph21") -> list[tuple[str, ...]]:
    from ..update.manifest import load

    return [g.terms for g in load(skill).groups.values()]


def keyword_excerpt(text: str, groups: list[tuple[str, ...]] | None = None, limit: int = 6000, head: int = 1500,
                    window: int = 500) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    if len(t) <= limit:
        return t
    lower = t.lower()
    per_group = [[m.start() for m in _RE_ARTICLE_21_26.finditer(t, head)]]
    for terms in manifest_terms() if groups is None else groups:
        per_group.append(sorted({m.start() for s in terms for m in re.finditer(re.escape(s.lower()), lower)
                                 if m.start() >= head}))
    per_group = [x for x in per_group if x]
    if not per_group:
        return t[:limit]
    return round_robin_spans(t, per_group, limit, head, window)


@dataclass(frozen=True)
class LLMClassification:
    category: str
    reason: str
    raw: str
    valid: bool


def user_message(regulation: str, title: str, subject: str = "", text: str | None = None) -> str:
    base = f"Jenis dan nomor: {regulation or '-'}\nJudul: {title}\nPerihal: {subject or '-'}"
    return base if text is None else f"{base}\nCuplikan teks:\n{text}"


def parse_answer(raw: str) -> LLMClassification:
    m = re.search(r"\{.*\}", raw or "", re.S)
    try:
        data = json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        data = None
    category = str(data.get("kategori", "")).strip().lower() if isinstance(data, dict) else ""
    if category not in LLM_CATEGORIES:
        return LLMClassification("perlu_ditinjau", f"jawaban LLM tidak valid: {(raw or '')[:120]!r}", raw or "", False)
    return LLMClassification(category, str(data.get("alasan", "")).strip(), raw, True)


class LLMCache:
    def __init__(self, path: Path | None):
        self.path = Path(path) if path else None
        self._records: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._f = None
        self.write_failures = 0
        if self.path and self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(r, dict) and "kunci" in r:
                    self._records[r["kunci"]] = r

    @staticmethod
    def make_key(model_id: str, repeat: int, user: str, system: str = SYSTEM_PROMPT, version: str = PROMPT_VERSION) -> str:
        material = json.dumps([model_id, version, repeat, system, user], ensure_ascii=False)
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def get(self, key: str) -> dict | None:
        return self._records.get(key)

    def put(self, record: dict) -> None:
        with self._lock:
            self._records[record["kunci"]] = record
            if not self.path:
                return
            line = json.dumps(record, ensure_ascii=False) + "\n"
            for i in range(6):
                try:
                    if self._f is None:
                        self.path.parent.mkdir(parents=True, exist_ok=True)
                        self._f = open(self.path, "a", encoding="utf-8")  # noqa: SIM115
                    self._f.write(line)
                    self._f.flush()
                    return
                except OSError:
                    self._close()
                    time.sleep(0.2 * 2 ** i)
            self.write_failures += 1

    def _close(self) -> None:
        if self._f is not None:
            with contextlib.suppress(OSError):
                self._f.close()
            self._f = None

    def close(self) -> None:
        with self._lock:
            self._close()


@dataclass
class LLMClassifier:
    call: LLMCall
    model_id: str
    cache: LLMCache
    repeats: int = 0
    attempts: int = 3
    system: str = SYSTEM_PROMPT
    version: str = PROMPT_VERSION

    @classmethod
    def with_text(cls, call: LLMCall, model_id: str, cache: LLMCache, repeat: int = 0) -> LLMClassifier:
        return cls(call, model_id, cache, repeat, system=TEXT_SYSTEM_PROMPT, version=TEXT_PROMPT_VERSION)

    @classmethod
    def with_keyword_text(cls, call: LLMCall, model_id: str, cache: LLMCache, repeat: int = 0) -> LLMClassifier:
        return cls(call, model_id, cache, repeat, system=KEYWORD_TEXT_SYSTEM_PROMPT, version=KEYWORD_TEXT_PROMPT_VERSION)

    def classify(self, regulation: str, title: str, subject: str = "", text: str | None = None) -> LLMClassification:
        raw, error = self._complete(user_message(regulation, title, subject, text), regulation, title)
        if raw is None:
            return LLMClassification("perlu_ditinjau", f"panggilan LLM gagal: {error}", "", False)
        return parse_answer(raw)

    def _complete(self, user: str, regulation: str, title: str) -> tuple[str | None, Exception | None]:
        key = LLMCache.make_key(self.model_id, self.repeats, user, self.system, self.version)
        cached = self.cache.get(key)
        if cached is not None:
            return cached["mentah"], None
        error = None
        for i in range(self.attempts):
            try:
                raw = self.call(self.system, user)
                break
            except Exception as exc:
                error = exc
                if i + 1 < self.attempts:
                    time.sleep(min(30.0, 2.0 * 2 ** i))
        else:
            return None, error
        self.cache.put({
            "kunci": key, "model": self.model_id, "prompt_versi": self.version,
            "ulangan": self.repeats, "identitas": regulation, "judul": title, "mentah": raw,
        })
        return raw, None

    def classify_many(self, inputs: list[tuple[str, str, str]], workers: int = 4, progress=None) -> list[LLMClassification]:
        result: list[LLMClassification | None] = [None] * len(inputs)
        done = [0]
        lock = threading.Lock()

        def work(i: int) -> None:
            result[i] = self.classify(*inputs[i])
            with lock:
                done[0] += 1
                if progress:
                    progress(done[0], len(inputs))

        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            list(ex.map(work, range(len(inputs))))
        return result  # type: ignore[return-value]


@dataclass
class LLMToolClassifier(LLMClassifier):
    max_steps: int = TOOLS_MAX_STEPS
    system: str = TOOLS_SYSTEM_PROMPT
    version: str = TOOLS_PROMPT_VERSION

    def classify(self, regulation: str, title: str, subject: str = "", text: str | None = None) -> LLMClassification:
        from .document_tools import DocumentTools

        tools = DocumentTools(text or "")
        transcript = [user_message(regulation, title, subject) + f"\nPanjang teks: {len(tools.text)} karakter. Mulai."]
        raw = ""
        for step in range(1, self.max_steps + 1):
            note = "" if step < self.max_steps else "\nIni langkah terakhir: jawab dengan aksi selesai."
            raw, error = self._complete("\n\n".join(transcript) + note, regulation, title)
            if raw is None:
                return LLMClassification("perlu_ditinjau", f"panggilan LLM gagal: {error}", "", False)
            m = re.search(r"\{.*\}", raw, re.S)
            try:
                data = json.loads(m.group(0)) if m else None
            except json.JSONDecodeError:
                data = None
            action = data.get("aksi") if isinstance(data, dict) else None
            if action == "cari":
                hits = tools.search(data.get("kueri", ""))
                transcript.append(f"Langkah {step}: cari {json.dumps(data.get('kueri'), ensure_ascii=False)}\nHasil: "
                                  + (json.dumps(hits, ensure_ascii=False) if hits else "tidak ada"))
            elif action == "baca":
                transcript.append(f"Langkah {step}: baca {data.get('posisi')}\nTeks: {tools.read(data.get('posisi'))}")
            else:
                k = parse_answer(raw)
                return LLMClassification(k.category, f"{k.reason} [{step} langkah]", raw, k.valid)
        return LLMClassification("perlu_ditinjau", "langkah habis tanpa jawaban", raw, False)


def langchain_call(provider: str | None = None, model: str | None = None) -> tuple[LLMCall, str]:
    from ..agent.runner import build_model, default_provider

    provider = (provider or default_provider()).lower()
    llm = build_model(model=model, temperature=0.0, provider=provider)
    if provider in ("azure", "openai"):
        llm = llm.bind(response_format={"type": "json_object"})
    name = model or (get_settings().azure_deployment if provider == "azure" else None) or "default"
    model_id = f"{provider}:{name}"

    def call(system: str, user: str) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage

        r = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        content = r.content
        if isinstance(content, list):
            content = "".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in content)
        return str(content)

    return call, model_id
