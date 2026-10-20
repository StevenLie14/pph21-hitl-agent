from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from taxagent.cli._common import llm_client  # noqa: E402
from taxagent.evaluation.scorer import reference_result  # noqa: E402
from taxagent.taxes.pph21.calc.rates import DATA_DIR  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "outputs"
VERSION = "hitung-sendiri-v1"
SYSTEM = ("Anda ahli Pajak Penghasilan Pasal 21 Indonesia (PMK 168/2023, PP 58/2023, UU PPh). Hitung PPh 21 terutang "
          "untuk kasus pengguna sesuai ketentuan yang berlaku pada tahun pajak kasus itu. Bila pertanyaan menyebut nilai "
          "bulanan untuk perhitungan setahun, setahunkan sendiri. Jawab HANYA JSON: "
          '{"pph_terutang": <angka rupiah bulat, tanpa titik/koma>, "langkah": "<ringkas, maks 5 baris>"}')
TABLE = ("\n\nGunakan tabel resmi berikut (YAML; berlaku sama untuk 2024 dan 2025):\n")
CODE_VERSION = "hitung-kode-v2"
CODE_STEPS = 4
CODE_TIMEOUT = 20
CODE_OUT_CHARS = 4000
CODE = ("\n\nAnda mempunyai interpreter Python 3 (pustaka standar saja, tanpa berkas dan jaringan). WAJIB: lakukan "
        "perhitungan dengan menjalankan kode minimal sekali sebelum jawaban akhir; kirim "
        '{"kode": "<program Python yang mencetak hasil dengan print>"} dan Anda menerima stdout/stderr-nya. Paling banyak '
        f"{CODE_STEPS} langkah; setiap langkah jawab HANYA satu JSON: kode, atau jawaban akhir di atas setelah melihat "
        "keluaran kode.")


CASE_FILES = {"dev": ("kasus_agent.yaml", "kasus_agent_holdout.yaml"),
              "heldout": ("kasus_agent_uji_resmi.yaml", "kasus_agent_uji_alami.yaml", "kasus_agent_uji_2026.yaml")}


def calculation_cases(which: str = "dev") -> list[dict]:
    result = []
    for f in CASE_FILES[which]:
        for k in yaml.safe_load((DATA_DIR / f).read_text(encoding="utf-8"))["kasus"]:
            if k.get("perilaku") != "hitung" or "pph_terutang" not in reference_result(k):
                continue
            result.append({**k, "dataset": f.removesuffix(".yaml")})
    return result


def number(v) -> int | None:
    try:
        return round(float(str(v).replace(".", "").replace(",", ".").replace("Rp", "").strip()))
    except (TypeError, ValueError):
        return None


def run_python(code: str) -> str:
    with tempfile.TemporaryDirectory() as d:
        try:
            p = subprocess.run([sys.executable, "-I", "-c", code], cwd=d, capture_output=True, text=True,
                               timeout=CODE_TIMEOUT, env={"PYTHONIOENCODING": "utf-8", "SYSTEMROOT": ""})
        except subprocess.TimeoutExpired:
            return f"(dihentikan: lebih dari {CODE_TIMEOUT} detik)"
    out = (p.stdout + ("\nSTDERR:\n" + p.stderr if p.stderr.strip() else "")).strip()
    return out[:CODE_OUT_CHARS] or "(tidak ada keluaran)"


def with_code(client, system: str, question: str, version: str) -> tuple[dict | None, int, int]:
    transcript, tokens, runs = [question], 0, 0
    for step in range(1, CODE_STEPS + 1):
        note = "" if step < CODE_STEPS else "\n\nIni langkah terakhir: beri jawaban akhir."
        data, record = client(system, "\n\n".join(transcript) + note, version)
        tokens += record.get("token_masuk", 0) + record.get("token_keluar", 0)
        if isinstance(data, dict) and isinstance(data.get("kode"), str) and "pph_terutang" not in data:
            runs += 1
            transcript.append(f"Langkah {step}, kode:\n{data['kode']}\nKeluaran:\n{run_python(data['kode'])}")
            continue
        return data, tokens, runs
    return None, tokens, runs


def main() -> None:
    ap = argparse.ArgumentParser(description="Comparison: the LLM computes PPh 21 itself, without the calculation skill, on the agent evaluation's calculation")
    ap.add_argument("--max", dest="max", type=int, default=0)
    ap.add_argument("--cases", choices=sorted(CASE_FILES), default="dev",
                    help="dev: the development calculation questions; heldout: the held-out ones")
    ap.add_argument("--provider", default="azure")
    ap.add_argument("--model", default=None)
    ap.add_argument("--conditions", nargs="+", default=["tanpa_data", "dengan_tabel", "dengan_kode"],
                    choices=["tanpa_data", "dengan_tabel", "dengan_kode"])
    ap.add_argument("--runs", type=int, default=1, help="run per kondisi (run ke-2 dst. punya kunci cache sendiri)")
    ap.add_argument("--tag", default="", help="suffix for the cache key, so every run is asked afresh (e.g. a re-run after the freeze)")
    a = ap.parse_args()
    client, model_id = llm_client(a.provider, a.model, OUT_DIR / "cache_llm" / "hitung_sendiri.jsonl")
    if client is None:
        sys.exit(1)
    table = (DATA_DIR / "tarif_2024.yaml").read_text(encoding="utf-8")
    cases = calculation_cases(a.cases)[:a.max or None]
    conditions = {n: p for n, p in {"tanpa_data": SYSTEM, "dengan_tabel": SYSTEM + TABLE + table,
                                    "dengan_kode": SYSTEM + TABLE + table + CODE}.items() if n in a.conditions}

    def one(arg: tuple[dict, str, int]) -> dict:
        k, name, run = arg
        ref = int(round(float(reference_result(k)["pph_terutang"])))
        version = (CODE_VERSION if name == "dengan_kode" else VERSION) + (f"-{a.tag}" if a.tag else "") + (f"-r{run + 1}" if run else "")
        if name == "dengan_kode":
            data, tokens, code_runs = with_code(client, conditions[name], k["pertanyaan"].strip(), version)
        else:
            data, record = client(conditions[name], k["pertanyaan"].strip(), version)
            tokens, code_runs = record.get("token_masuk", 0) + record.get("token_keluar", 0), 0
        value = number((data or {}).get("pph_terutang"))
        diff = None if value is None else value - ref
        return {"id": k["id"], "dataset": k["dataset"], "kategori": k["kategori"], "kondisi": name, "run": run + 1,
                "acuan": ref, "llm": value, "selisih": diff, "benar": diff is not None and abs(diff) <= 1,
                "dalam_1persen": diff is not None and abs(diff) <= max(1, abs(ref) * 0.01),
                "langkah": (data or {}).get("langkah"), "token": tokens, "jalan_kode": code_runs}

    with ThreadPoolExecutor(4) as ex:
        results = list(ex.map(one, [(k, n, r) for k in cases for n in conditions for r in range(a.runs)]))
    client.cache.close()
    summary = {}
    for n in conditions:
        xs = [h for h in results if h["kondisi"] == n]
        wrong = [abs(h["selisih"]) for h in xs if h["selisih"] is not None and not h["benar"]]
        per_case = {}
        for h in xs:
            per_case.setdefault(h["id"], []).append(h["benar"])
        summary[n] = {"n": len(xs), "benar": sum(h["benar"] for h in xs),
                      "dalam_1persen": sum(h["dalam_1persen"] for h in xs),
                      "tanpa_angka": sum(h["llm"] is None for h in xs),
                      "median_selisih_salah": sorted(wrong)[len(wrong) // 2] if wrong else 0,
                      "kasus_benar_semua_run": sum(all(v) for v in per_case.values()),
                      "kasus_tidak_stabil": sum(len(set(v)) > 1 for v in per_case.values()),
                      "token_rata": round(sum(h["token"] for h in xs) / len(xs)) if xs else 0,
                      "jalan_kode_rata": round(sum(h["jalan_kode"] for h in xs) / len(xs), 2) if xs else 0}
    name = OUT_DIR / (f"llm_hitung_sendiri_{dt.date.today():%Y%m%d}" + (f"_{a.cases}" if a.cases != "dev" else ""))
    OUT_DIR.mkdir(exist_ok=True)
    name.with_suffix(".json").write_text(json.dumps({"model": model_id, "versi": VERSION + (f"-{a.tag}" if a.tag else ""), "ringkas": summary,
                                                     "kasus": results}, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    md = [f"# LLM menghitung PPh 21 sendiri ({model_id}, {len(cases)} kasus, {a.runs} run per kondisi)", "",
          "| kondisi | benar (selisih <= Rp1) | dalam 1% | tanpa angka | median selisih yang salah | kasus benar di semua run "
          "| kasus tidak stabil | token rata-rata | jalan kode rata-rata |",
          "|---|---|---|---|---|---|---|---|---|"]
    md += [f"| {n} | {r['benar']}/{r['n']} | {r['dalam_1persen']}/{r['n']} | {r['tanpa_angka']} | "
           f"Rp{r['median_selisih_salah']:,} | {r['kasus_benar_semua_run']}/{len(cases)} | {r['kasus_tidak_stabil']} | "
           f"{r['token_rata']:,} | {r['jalan_kode_rata']} |" for n, r in summary.items()]
    md += ["", "Acuan: mesin hitung deterministik pada argumen yang diharapkan; kebenaran mesin sendiri dari uji emas "
           "contoh lampiran resmi, jadi angka di sini mengukur selisih LLM terhadap mesin."]
    name.with_suffix(".md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
