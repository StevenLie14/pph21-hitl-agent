from __future__ import annotations

import hashlib
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..paths import PIPELINE_DIR
from ..settings import get_settings

CACHE_DIR = Path("outputs/ocr_berkas")
SCRIPT = PIPELINE_DIR / "ocr_file.py"
DEFAULT_COMMAND = "conda run -n ocr_gpu python {skrip} {pdf} {keluaran} --device gpu"


@dataclass
class OCRResult:
    text: str | None
    pdf_kind: str | None
    source: str
    error: str | None = None


def ocr_command() -> list[str]:
    return shlex.split(get_settings().ocr_cmd or DEFAULT_COMMAND, posix=True)


def ocr_if_scanned(content: bytes, cache: Path = CACHE_DIR, run=subprocess.run, timeout_s: int = 3600) -> OCRResult:
    from .text_quality import pdf_kind

    kind = pdf_kind(content)
    if kind != "scan":
        return OCRResult(None, kind, "lapisan_pdf")
    h = hashlib.sha1(content).hexdigest()
    cache_file = cache / f"{h}.txt"
    if cache_file.exists():
        return OCRResult(cache_file.read_text(encoding="utf-8"), kind, "ocr_cache")
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        pdf, out = Path(tmp) / f"{h}.pdf", Path(tmp) / f"{h}.txt"
        pdf.write_bytes(content)
        cmd = [x.replace("{skrip}", str(SCRIPT)).replace("{pdf}", str(pdf)).replace("{keluaran}", str(out))
               for x in ocr_command()]
        cmd[0] = shutil.which(cmd[0]) or cmd[0]
        try:
            r = run(cmd, capture_output=True, text=True, timeout=timeout_s)
        except (OSError, subprocess.TimeoutExpired) as e:
            return OCRResult(None, kind, "lapisan_pdf", f"{type(e).__name__}: {e}")
        if r.returncode != 0 or not out.exists() or not out.read_text(encoding="utf-8").strip():
            message = (r.stderr or r.stdout or "").strip().splitlines()[-1:] or ["keluaran kosong"]
            return OCRResult(None, kind, "lapisan_pdf", f"exit {r.returncode}: {message[0][:200]}")
        text = out.read_text(encoding="utf-8")
    cache_file.write_text(text, encoding="utf-8")
    return OCRResult(text, kind, "ocr")
