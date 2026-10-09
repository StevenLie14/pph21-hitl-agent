from __future__ import annotations

import subprocess
import time
from pathlib import Path

ENGINE = "PaddleOCR PP-OCRv6 medium, lang id, 300 dpi"
DPI = 300


def make_ocr(device: str = "gpu", threads: int = 5):
    from paddleocr import PaddleOCR

    return PaddleOCR(lang="id", use_doc_orientation_classify=False, use_doc_unwarping=False,
                     use_textline_orientation=False, enable_mkldnn=False, cpu_threads=threads, device=device)


def ocr_page(ocr, page, png: Path) -> str:
    page.get_pixmap(dpi=DPI).save(png)
    try:
        return "\n".join(t for r in ocr.predict(str(png)) for t in r["rec_texts"])
    finally:
        png.unlink(missing_ok=True)


def gpu_temperature() -> int | None:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10).stdout
        return int(out.split()[0])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


class Pause:
    def __init__(self, work_minutes: float = 120, pause_minutes: float = 30, state_file: Path | None = None,
                 max_temp: int = 87, resume_temp: int = 75):
        self.work, self.pause = work_minutes * 60, pause_minutes * 60
        self.state_file = state_file
        self.max_temp, self.resume_temp = max_temp, resume_temp
        self._last_temp_check = 0.0
        self.start = time.time()
        if state_file and state_file.exists():
            try:
                previous = float(state_file.read_text(encoding="utf-8"))
            except ValueError:
                previous = 0.0
            if self.start - previous < self.work + self.pause:
                self.start = previous
        self._save()

    def _save(self) -> None:
        if self.state_file:
            self.state_file.write_text(str(self.start), encoding="utf-8")

    def check_temperature(self) -> None:
        if not self.max_temp or time.time() - self._last_temp_check < 30:
            return
        self._last_temp_check = time.time()
        temp = gpu_temperature()
        if temp is None or temp < self.max_temp:
            return
        print(f"suhu GPU {temp} C >= {self.max_temp} C: jeda sampai <= {self.resume_temp} C "
              f"({time.strftime('%H:%M')})", flush=True)
        while temp is not None and temp > self.resume_temp:
            time.sleep(60)
            temp = gpu_temperature()
        print(f"suhu GPU {temp} C, OCR lanjut ({time.strftime('%H:%M')})", flush=True)

    def check(self) -> None:
        self.check_temperature()
        if self.work and time.time() - self.start >= self.work:
            resume = time.strftime("%H:%M", time.localtime(time.time() + self.pause))
            print(f"jeda {self.pause / 60:.0f} menit (mendinginkan GPU), lanjut {resume}", flush=True)
            time.sleep(self.pause)
            self.start = time.time()
            self._save()


def add_pause_arguments(ap, work_minutes: float = 120, pause_minutes: float = 30) -> None:
    ap.add_argument("--work-minutes", dest="work_minutes", type=float, default=work_minutes,
                    help="lama kerja sebelum jeda (0 = tanpa jeda)")
    ap.add_argument("--pause-minutes", dest="pause_minutes", type=float, default=pause_minutes,
                    help="lama jeda")
    ap.add_argument("--max-temp", dest="max_temp", type=int, default=87,
                    help="jeda bila suhu GPU mencapai ini, sampai <= 75 (0 = tanpa cek)")
