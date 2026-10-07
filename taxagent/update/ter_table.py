from __future__ import annotations

import base64
import hashlib
import json
import re
import shlex
import shutil
import statistics
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from ..paths import PIPELINE_DIR
from ..settings import get_settings
from .amounts import clean_text, yaml_number
from .extraction import ExtractionResult, Finding
from .llm import LLMResult, leaves

CACHE_DIR = Path("outputs/ocr_kotak")
SCRIPT = PIPELINE_DIR / "ocr_boxes.py"
DEFAULT_COMMAND = "conda run -n ocr_gpu python {skrip} {pdf} {keluaran} --pages {halaman} --device gpu"

DAILY = "harian"
_RE_TITLE = re.compile(r"^\s*[A-Z]\s*[.,]?\s*TARIF\s+EFEKTIF\s+(?:BULANAN\s+KATEGORI\s+([A-Z])\b|(HARIAN))")
_RE_MARK = re.compile(r"TARIF\s+EFEKTIF\s+(?:BULANAN|HARIAN)", re.I)
_RE_LIMIT = re.compile(r"(DI ?ATAS|SAMPAI ?DENGAN) RP(\??)(\d+(?:\.\d+)?)")
_RE_PERCENT = re.compile(r"(?<![\w.?])(\??)(\d+(?:\.\d+)?)%")


@dataclass
class Row:
    lower: Decimal | None
    upper: Decimal | None
    percent: Decimal
    page: int = 0


@dataclass
class TableResult:
    table: dict[str, list[Row]] = field(default_factory=dict)
    raw: dict[str, list[Row]] = field(default_factory=dict)
    title: list[str] = field(default_factory=list)
    quote: dict[str, str] = field(default_factory=dict)
    verified: set[Decimal] = field(default_factory=set)
    without_words: set[Decimal] = field(default_factory=set)
    mismatches: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def has_ter_table(text: str) -> bool:
    return bool(_RE_MARK.search(text or ""))


def check_structure(rows: list[Row]) -> list[str]:
    errors = []
    if not rows:
        return ["tidak ada baris"]
    if rows[0].lower is not None:
        errors.append(f"baris 1 tidak diawali 'sampai dengan' (batas bawah {rows[0].lower})")
    for i, (a, b) in enumerate(zip(rows, rows[1:]), 2):
        if a.upper is None:
            errors.append(f"baris {i - 1} terbuka ('di atas' tanpa batas atas) padahal bukan baris terakhir")
            continue
        if b.lower != a.upper:
            errors.append(f"baris {i}: batas bawah {b.lower} != batas atas baris sebelumnya {a.upper}")
        if b.upper is not None and b.upper <= a.upper:
            errors.append(f"baris {i}: batas atas {b.upper} tidak naik dari {a.upper}")
        if b.percent < a.percent:
            errors.append(f"baris {i}: tarif {b.percent}% turun dari {a.percent}%")
    for i, r in enumerate(rows, 1):
        if not (0 <= r.percent <= 100):
            errors.append(f"baris {i}: tarif {r.percent}% di luar 0-100")
    return errors


def yaml_values(table: dict[str, list[Row]]) -> dict:
    def brackets(bs):
        return [{"batas_atas": None if r.upper is None else yaml_number(r.upper), "persen": yaml_number(r.percent)}
                for r in bs]

    out: dict = {}
    monthly = {k: brackets(v) for k, v in sorted(table.items()) if k != DAILY}
    if monthly:
        out["ter_bulanan"] = monthly
    if DAILY in table:
        out["ter_harian"] = {"lapisan": brackets(table[DAILY])}
    return out


def _filter(h: TableResult, table: dict[str, list[Row]], label: str) -> dict[str, list[Row]]:
    passed = {}
    for k, bs in table.items():
        errors = check_structure(bs)
        if errors:
            h.notes.append(f"{label} kategori {k}: struktur tabel rusak, tidak dipakai ({'; '.join(errors[:3])})")
        else:
            passed[k] = bs
    monthly_titles = [k for k in h.title if k != DAILY]
    failed = [k for k in monthly_titles if k not in passed]
    if failed:
        h.notes.append(f"{label}: kategori {', '.join(failed)} tidak terbaca utuh; ter_bulanan tidak dipakai "
                         "(semua kategori atau tidak sama sekali)")
        passed = {k: v for k, v in passed.items() if k == DAILY}
    return passed


def table_pages(content: bytes) -> list[int]:
    import pymupdf

    with pymupdf.open(stream=content, filetype="pdf") as doc:
        text = [p.get_text() for p in doc]
    if sum(len(t.strip()) for t in text) < 50 * len(text):
        return list(range(1, len(text) + 1))
    selected = [i for i, t in enumerate(text, 1)
             if _RE_MARK.search(t) or (re.search(r"di\s+atas", t, re.I) and re.search(r"Rp", t))]
    return selected


def _range(pages: list[int]) -> str:
    parts, start = [], None
    for i, p in enumerate(pages):
        if start is None:
            start = p
        if i + 1 == len(pages) or pages[i + 1] != p + 1:
            parts.append(str(start) if start == p else f"{start}-{p}")
            start = None
    return ",".join(parts)


def ocr_command() -> list[str]:
    return shlex.split(get_settings().ocr_box_cmd or DEFAULT_COMMAND, posix=True)


def ocr_boxes(content: bytes, pages: list[int], cache: Path = CACHE_DIR, run=subprocess.run,
              timeout_s: int = 3600) -> tuple[dict | None, str | None]:
    ranges = _range(pages)
    h = hashlib.sha1(content).hexdigest()
    cache_file = cache / f"{h}_{ranges.replace(',', '_')}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8")), None
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        pdf, out = Path(tmp) / f"{h}.pdf", Path(tmp) / f"{h}.json"
        pdf.write_bytes(content)
        cmd = [x.replace("{skrip}", str(SCRIPT)).replace("{pdf}", str(pdf)).replace("{keluaran}", str(out))
               .replace("{halaman}", ranges) for x in ocr_command()]
        cmd[0] = shutil.which(cmd[0]) or cmd[0]
        try:
            r = run(cmd, capture_output=True, text=True, timeout=timeout_s)
        except (OSError, subprocess.TimeoutExpired) as e:
            return None, f"{type(e).__name__}: {e}"
        if r.returncode != 0 or not out.exists():
            message = (r.stderr or r.stdout or "").strip().splitlines()[-1:] or ["keluaran kosong"]
            return None, f"exit {r.returncode}: {message[0][:200]}"
        data = json.loads(out.read_text(encoding="utf-8"))
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data, None


def _column_bounds(page: dict) -> float | None:
    w = page["lebar"]
    boxes = page["kotak"]
    filled = [k for k in boxes if re.search(r"Rp|\d\s*%", k["teks"])]
    if not filled:
        return None
    y0, y1 = min(k["y0"] for k in filled), max(k["y1"] for k in filled)
    ranges = sorted((k["x0"], k["x1"]) for k in boxes
                     if k["y1"] >= y0 and k["y0"] <= y1 and (k["x1"] - k["x0"]) < 0.6 * w)
    gaps, edge = [], None
    for a, b in ranges:
        if edge is not None and a > edge:
            gaps.append((edge, a))
        edge = b if edge is None else max(edge, b)
    gaps = [(a, b) for a, b in gaps if 0.35 * w <= (a + b) / 2 <= 0.9 * w]
    if not gaps:
        return None
    a, b = max(gaps, key=lambda c: c[1] - c[0])
    return (a + b) / 2


def _screen_rows(boxes: list[dict]) -> list[dict]:
    if not boxes:
        return []
    height = statistics.median(k["y1"] - k["y0"] for k in boxes)
    ordered = sorted(boxes, key=lambda k: (k["y0"] + k["y1"]) / 2)
    result, group, anchor = [], [], None
    for k in ordered:
        yc = (k["y0"] + k["y1"]) / 2
        if anchor is not None and yc - anchor > 0.5 * height:
            result += sorted(group, key=lambda x: x["x0"])
            group = []
            anchor = None
        if anchor is None:
            anchor = yc
        group.append(k)
    return result + sorted(group, key=lambda x: x["x0"])


def _columns(data: dict) -> tuple[dict[str, list[tuple[int, str]]], dict[str, list[tuple[int, str]]], list[str], list[str]]:
    notes: list[str] = []
    split = {h["nomor"]: _column_bounds(h) for h in data["halaman"]}
    ratios = [b / h["lebar"] for h in data["halaman"] if (b := split[h["nomor"]]) is not None]
    fallback = statistics.median(ratios) if ratios else None
    left: dict[str, list[tuple[int, str]]] = {}
    right: dict[str, list[tuple[int, str]]] = {}
    titles: list[str] = []
    category = None
    for h in data["halaman"]:
        b = split[h["nomor"]]
        if b is None:
            if fallback is None:
                continue
            b = fallback * h["lebar"]
            if any(re.search(r"Rp", k["teks"]) for k in h["kotak"]):
                notes.append(f"hal {h['nomor']}: celah kolom tidak terlihat, memakai posisi rata-rata halaman lain")
        page_titles = sorted((k["y0"], m.group(1) or DAILY) for k in h["kotak"]
                        if (m := _RE_TITLE.match(k["teks"].upper())))
        plain = [k for k in h["kotak"] if not _RE_TITLE.match(k["teks"].upper())]
        for k in _screen_rows(plain):
            box_category = category
            for y, name in page_titles:
                if y <= k["y0"]:
                    box_category = name
            if box_category is None:
                continue
            (left if k["x0"] < b else right).setdefault(box_category, []).append((h["nomor"], k["teks"]))
        for _, name in page_titles:
            if name not in titles:
                titles.append(name)
            category = name
    return left, right, titles, notes


def read_columns(data: dict) -> TableResult:
    h = TableResult()
    left, right, h.title, h.notes = _columns(data)
    raw: dict[str, list[Row]] = {}
    for category in h.title:
        bk = clean_text(" ".join(t for _, t in left.get(category, [])))
        bp = clean_text(" ".join(t for _, t in right.get(category, [])))
        for b in (bk, bp):
            h.verified |= b.verified
            h.without_words |= b.without_words
            h.mismatches += [f"tabel {category}: {x}" for x in b.mismatches]
        h.quote[category] = f"{bk.text} | {bp.text}"
        ranges: list[tuple[Decimal | None, Decimal | None]] = []
        lower = None
        for m in _RE_LIMIT.finditer(bk.text):
            v = Decimal(m.group(3))
            if m.group(1).startswith("DI"):
                if lower is not None:
                    ranges.append((lower, None))
                lower = v
            else:
                ranges.append((lower, v))
                lower = None
        if lower is not None:
            ranges.append((lower, None))
        percent = [Decimal(m.group(2)) for m in _RE_PERCENT.finditer(bp.text)]
        if len(ranges) != len(percent):
            h.notes.append(f"OCR kategori {category}: {len(ranges)} rentang penghasilan tetapi {len(percent)} tarif; "
                             "tidak dipakai")
            continue
        raw[category] = [Row(a, b, p) for (a, b), p in zip(ranges, percent)]
    h.raw = raw
    h.table = _filter(h, raw, "OCR")
    return h


def findings_from(h: TableResult, source: str) -> ExtractionResult:
    e = ExtractionResult(mismatches=list(h.mismatches), notes=list(h.notes),
                       verified=set(h.verified), without_words=set(h.without_words))
    values = yaml_values(h.table)
    for key, v in values.items():
        categories = [DAILY] if key == "ter_harian" else [k for k in h.table if k != DAILY]
        e.findings.append(Finding(key, v, " || ".join(f"[{k}] {h.quote[k]}" for k in categories), source))
    return e


VISION_PROMPT_VERSION = "ter-visi-v1-2026-10-17"
VISION_DPI = 200

VISION_PROMPT = """\
Anda menyalin tabel tarif dari gambar SATU halaman lampiran peraturan perpajakan Indonesia, untuk diperiksa \
silang dengan ekstraktor lain. Salin apa yang tertulis di gambar; jangan menghitung, melengkapi baris yang \
tidak terlihat, atau memakai pengetahuan Anda tentang tarif yang berlaku.

Untuk setiap baris tabel di halaman ini, urut dari atas:
- judul: judul bagian tabel yang tertulis DI HALAMAN INI di atas baris itu, disalin persis (mis. \
"A. TARIF EFEKTIF BULANAN KATEGORI A", "D. TARIF EFEKTIF HARIAN"); null bila tidak ada judul di atas baris \
itu pada halaman ini (halaman lanjutan)
- batas_bawah: angka rupiah setelah "di atas"; null bila baris hanya bertuliskan "sampai dengan ..."
- batas_atas: angka rupiah setelah "sampai dengan"; null bila baris hanya bertuliskan "di atas ..."
- persen: tarif pajak baris itu

Aturan nilai: rupiah sebagai bilangan bulat tanpa pemisah (Rp5.400.000,00 -> 5400000); persen sebagai \
bilangan (0,25% -> 0.25; 5% -> 5). Halaman tanpa tabel tarif: "baris" kosong.

Jawab HANYA JSON: {"baris": [{"judul": null, "batas_bawah": 0, "batas_atas": 0, "persen": 0}]}"""


def page_image(content: bytes, pages: list[int], dpi: int = VISION_DPI) -> list[tuple[int, bytes]]:
    import pymupdf

    with pymupdf.open(stream=content, filetype="pdf") as doc:
        return [(p, doc[p - 1].get_pixmap(dpi=dpi).tobytes("png")) for p in pages]


def langchain_vision_call(provider: str | None = None, model: str | None = None):
    from ..agent.runner import build_model, default_provider

    provider = (provider or default_provider()).lower()
    m = build_model(model=model, temperature=0.0, provider=provider)
    if provider in ("azure", "openai"):
        m = m.bind(response_format={"type": "json_object"})
    name = model or (get_settings().azure_deployment if provider == "azure" else None) or "default"

    def call(system: str, png: bytes) -> dict:
        from langchain_core.messages import HumanMessage, SystemMessage

        url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
        r = m.invoke([SystemMessage(content=system), HumanMessage(content=[
            {"type": "text", "text": "Gambar halaman lampiran:"},
            {"type": "image_url", "image_url": {"url": url}},
        ])])
        u = getattr(r, "usage_metadata", None) or {}
        content = r.content if isinstance(r.content, str) else "".join(
            x.get("text", "") if isinstance(x, dict) else str(x) for x in r.content)
        return {"teks": content, "token_masuk": u.get("input_tokens", 0), "token_keluar": u.get("output_tokens", 0)}

    return call, f"{provider}:{name}"


@dataclass
class VisionClient:
    call: object
    model_id: str
    cache: object
    attempts: int = 3

    def __call__(self, system: str, png: bytes, version: str) -> tuple[dict | None, dict]:
        from ..monitor.impact import _json

        key = self.cache.make_key(self.model_id, 0, "gambar sha1 " + hashlib.sha1(png).hexdigest(), system, version)
        entry = self.cache.get(key)
        if entry is None:
            error = None
            for i in range(self.attempts):
                try:
                    t0 = time.perf_counter()
                    r = self.call(system, png)
                    entry = {"kunci": key, "model": self.model_id, "prompt_versi": version, "ulangan": 0,
                             "mentah": r["teks"], "token_masuk": r.get("token_masuk", 0),
                             "token_keluar": r.get("token_keluar", 0), "detik": time.perf_counter() - t0}
                    self.cache.put(entry)
                    break
                except Exception as exc:  # noqa: BLE001
                    error = exc
                    if i + 1 < self.attempts:
                        time.sleep(min(30.0, 2.0 * 2 ** i))
            if entry is None:
                return None, {"galat": str(error)}
        return _json(entry["mentah"]), entry


def vision_client(provider: str | None, model: str | None, cache: str | Path) -> VisionClient:
    from ..monitor.classify_llm import LLMCache

    call, model_id = langchain_vision_call(provider, model)
    return VisionClient(call, model_id, LLMCache(Path(cache)))


def _number(v) -> Decimal | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        return Decimal(str(v).replace(",", "."))
    except InvalidOperation:
        return None


def read_with_vision(images: list[tuple[int, bytes]], client) -> tuple[TableResult, LLMResult]:
    h, llm = TableResult(), LLMResult(group=["ter_bulanan", "ter_harian"])
    raw: dict[str, list[Row]] = {}
    category = None
    for p, png in images:
        data, record = client(VISION_PROMPT, png, VISION_PROMPT_VERSION)
        llm.tokens += int(record.get("token_masuk", 0)) + int(record.get("token_keluar", 0))
        if data is None or not isinstance(data.get("baris"), list):
            llm.valid = False
            llm.error = (llm.error + "; " if llm.error else "") + f"hal {p}: {record.get('galat') or 'jawaban bukan JSON'}"
            continue
        for b in data["baris"]:
            if not isinstance(b, dict):
                continue
            m = _RE_TITLE.match(str(b.get("judul") or "").upper())
            if m:
                category = m.group(1) or DAILY
                if category not in h.title:
                    h.title.append(category)
            percent = _number(b.get("persen"))
            if category is None or percent is None:
                llm.dropped.append(f"hal {p}: baris tanpa kategori atau tarif ({b})")
                continue
            raw.setdefault(category, []).append(Row(_number(b.get("batas_bawah")), _number(b.get("batas_atas")),
                                                    percent, p))
    h.raw = raw
    h.table = _filter(h, raw, "LLM vision")
    llm.dropped += h.notes
    for key, v in yaml_values(h.table).items():
        leaves(v, key, llm.values)
    return h, llm


def compare_reference(h: TableResult, reference: dict, raw: bool = False) -> dict:
    out = {}
    values = yaml_values(h.raw if raw else h.table)
    pairs = [(k, values.get("ter_bulanan", {}).get(k), v) for k, v in reference.get("ter_bulanan", {}).items()]
    pairs.append((DAILY, values.get("ter_harian", {}).get("lapisan"), reference.get("ter_harian", {}).get("lapisan")))
    for k, read, expected in pairs:
        if expected is None:
            continue
        expected_cells = leaves(expected, k)
        read_cells = leaves(read, k) if read is not None else {}
        errors = [f"{j}: dibaca {read_cells.get(j, 'tidak ada')}, acuan {v}" for j, v in expected_cells.items()
                 if read_cells.get(j, "x") != v]
        errors += [f"{j}: baris lebih ({read_cells[j]})" for j in read_cells if j not in expected_cells]
        out[k] = {"baris_acuan": len(expected), "baris_dibaca": len(read or []), "sel": len(expected_cells),
                     "benar": len(expected_cells) - sum(1 for j in expected_cells if read_cells.get(j, "x") != expected_cells[j]),
                     "salah": errors}
    return out


@dataclass
class TableRead:
    extraction: ExtractionResult | None
    llm: LLMResult | None
    lines: list[str] = field(default_factory=list)


def read_table(content: bytes, name: str, vision=None) -> TableRead:
    pages = table_pages(content)
    if not pages:
        return TableRead(None, None, ["tidak ada halaman tabel TER"])
    lines = [f"Tabel TER di lampiran: OCR kotak {len(pages)} halaman"]
    data, err = ocr_boxes(content, pages)
    if data is None:
        return TableRead(None, None, lines + [f"PERINGATAN: OCR kotak gagal ({err}); tabel TER tidak dibaca "
                                              "(key-nya tidak ditemukan)"])
    a = read_columns(data)
    lines.append(f"  OCR: {', '.join(f'{k} {len(v)} baris' for k, v in a.table.items()) or 'tidak ada tabel lolos struktur'}")
    lines += [f"  {c}" for c in a.notes]
    llm = None
    if vision is not None:
        b, llm = read_with_vision(page_image(content, pages), vision)
        lines.append(f"  LLM vision: {', '.join(f'{k} {len(v)} baris' for k, v in b.table.items()) or 'tidak ada tabel lolos struktur'}"
                     + (f"; tidak valid: {llm.error}" if not llm.valid else ""))
        lines += [f"  {c}" for c in b.notes]
    return TableRead(findings_from(a, name), llm, lines)
