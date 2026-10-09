from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

import psutil
import pymupdf
from paddle_common import ENGINE, Pause, add_pause_arguments, make_ocr, ocr_page

DEFAULT_DIR = Path(os.environ.get("PPH21_DATA") or "data") / "korpus_jdih"
NON_REGULATIONS = ("Artikel Hukum", "Monografi Hukum", "Putusan Pengadilan")


class MemoryLimit(Exception):
    pass


OOM = "oom_ocr.txt"
_GPU_EXHAUSTED = re.compile(r"out of memory|ALLOCATION_FAILED", re.I)
PPH21_CHAIN = Path(__file__).resolve().parents[1] / "taxagent" / "taxes" / "pph21" / "data" / "rantai_pph21.yaml"
_RE_TAX = re.compile(r"pajak|perpajakan|\bpph\b|\bppn\b|penghasilan|bea meterai", re.I)


def _chain_ids() -> set[str]:
    if not PPH21_CHAIN.exists():
        return set()
    return set(re.findall(r"id_jdih: ([0-9a-f-]{36})", PPH21_CHAIN.read_text(encoding="utf-8")))


def _title(d: Path, i: str) -> str:
    try:
        return json.loads((d / "halaman" / f"{i}.json").read_text(encoding="utf-8")).get("judul") or ""
    except (json.JSONDecodeError, OSError):
        return ""


def priority(d: Path, b: dict, chain: set[str]) -> int:
    if b.get("bentuk") in NON_REGULATIONS:
        return 3
    if b["id"] in chain:
        return 0
    return 1 if _RE_TAX.search(_title(d, b["id"])) else 2


def jobs(d: Path) -> list[dict]:
    result = []
    for f in (d / "berkas").glob("*.json"):
        try:
            b = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if (b.get("jenis") == "scan" and not (d / "teks" / f"{b['id']}.txt").exists()
                and not (d / "ocr_dikirim" / f"{b['id']}.json").exists()):
            result.append(b)
    oom = Counter((d / OOM).read_text(encoding="utf-8").split()) if (d / OOM).exists() else Counter()
    result = [b for b in result if oom[b["id"]] < 2]
    chain = _chain_ids()
    return sorted(result, key=lambda b: (priority(d, b, chain), b.get("halaman", 0)))


def ocr_document(ocr, d: Path, b: dict, pause: Pause | None = None, max_memory: float = 0) -> None:
    i = b["id"]
    folder = d / "ocr" / i
    folder.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with pymupdf.open(d / "pdf" / f"{i}.pdf") as doc:
        n_pages = doc.page_count
        for p, page in enumerate(doc, 1):
            f = folder / f"{p:04d}.txt"
            if f.exists():
                continue
            if pause:
                pause.check()
            f.write_text(ocr_page(ocr, page, folder / "_hal.png"), encoding="utf-8")
            if max_memory and psutil.Process().memory_info().private > max_memory:
                raise MemoryLimit(f"memori proses > {max_memory / 2**30:.0f} GB setelah halaman {p} dari {n_pages}")
    pages = sorted(folder.glob("[0-9]*.txt"))
    text = "\n".join(x.read_text(encoding="utf-8") for x in pages)
    (d / "teks" / f"{i}.txt").write_text(text, encoding="utf-8")
    (d / "ocr" / f"{i}.json").write_text(json.dumps({"id": i, "halaman": n_pages, "mesin": ENGINE,
                                                      "sumber_teks": "ocr_paddle"}), encoding="utf-8")
    print(f"SELESAI {i} ({b.get('bentuk')}) {n_pages} hal {time.time() - t0:.0f}s", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    ap.add_argument("--device", default="gpu")
    ap.add_argument("--threads", dest="threads", type=int, default=5)
    ap.add_argument("--follow", dest="follow", action="store_true",
                    help="tunggu PDF scan baru sampai unduhan selesai")
    ap.add_argument("--max-documents", dest="max_documents", type=int, default=0,
                    help="keluar (kode 3) setelah N dokumen berhasil; 0 = tanpa batas")
    ap.add_argument("--max-memory-gb", dest="max_memory_gb", type=float, default=10,
                    help="bersama --max-documents: keluar (kode 3) bila memori privat proses melewati batas ini")
    add_pause_arguments(ap)
    a = ap.parse_args()
    pause = Pause(a.work_minutes, a.pause_minutes, a.dir / "jeda_ocr.txt", max_temp=a.max_temp)

    ocr = make_ocr(a.device, a.threads)
    (a.dir / "teks").mkdir(parents=True, exist_ok=True)
    failed: set[str] = set()
    succeeded = 0
    max_memory = a.max_memory_gb * 2**30 if a.max_documents else 0
    while True:
        downloads_done = (a.dir / "unduh_selesai").exists()
        pending = [b for b in jobs(a.dir) if b["id"] not in failed]
        if pending:
            print(f"{len(pending)} PDF scan menunggu OCR", flush=True)
        for b in pending[:20]:
            try:
                ocr_document(ocr, a.dir, b, pause, max_memory)
                succeeded += 1
            except MemoryLimit as e:
                print(f"{e}, proses dimulai ulang untuk melepas memori", flush=True)
                sys.exit(3)
            except Exception as e:
                if a.max_documents and _GPU_EXHAUSTED.search(str(e)):
                    with open(a.dir / OOM, "a", encoding="utf-8") as f:
                        f.write(b["id"] + "\n")
                    print(f"memori GPU habis pada {b['id']}, proses dimulai ulang", flush=True)
                    sys.exit(3)
                failed.add(b["id"])
                print(f"GAGAL {b['id']}: {type(e).__name__}: {e}", flush=True)
                with open(a.dir / "gagal.jsonl", "a", encoding="utf-8") as f:
                    f.write(json.dumps({"langkah": "ocr", "kunci": b["id"], "galat": str(e)[:300]}) + "\n")
            if a.max_documents and succeeded >= a.max_documents:
                print(f"batas {a.max_documents} dokumen tercapai, proses dimulai ulang untuk melepas memori",
                      flush=True)
                sys.exit(3)
        if not pending:
            if downloads_done or not a.follow:
                break
            time.sleep(120)
    print("OCR selesai", flush=True)


if __name__ == "__main__":
    main()
