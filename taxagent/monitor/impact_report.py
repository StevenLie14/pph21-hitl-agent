from __future__ import annotations

import statistics

from .impact import score

ARMS = ("aturan", "llm", "llm_graf", "llm_graf_saring", "kaskade", "gabungan_utuh")


def _arms(results: dict) -> list[str]:
    run = {a for h in results.values() for a in h}
    return [a for a in ARMS if a in run]


def _pct(x) -> str:
    return "-" if x is None else f"{100 * x:.1f}%"


def summarize(results: dict, label: dict[str, set[str]], non_base: set[str],
            price_in: float, price_out: float) -> dict[str, dict]:
    per_arm = {}
    for nl in _arms(results):
        d, nd = score({i: h[nl].keys for i, h in results.items()}, label, non_base)
        hs = [h[nl] for h in results.values()]
        lat = sorted(h.seconds for h in hs)
        tokens_in, tokens_out = sum(h.tokens_in for h in hs), sum(h.tokens_out for h in hs)
        cost = (tokens_in * price_in + tokens_out * price_out) / 1e6
        per_arm[nl] = {
            "dasar": {"n": d.n, "tp": d.tp, "fp": d.fp, "fn": d.fn, "presisi": d.precision, "recall": d.recall,
                      "f1": d.f1, "set_tepat": d.exact},
            "bukan_dasar": {"n": nd.n, "dokumen_dengan_key": nd.violations, "key_palsu": nd.fp},
            "token_masuk": tokens_in, "token_keluar": tokens_out, "biaya_usd": cost,
            "biaya_usd_per_dokumen": cost / len(hs) if hs else 0,
            "latensi_median_detik": statistics.median(lat) if lat else 0,
            "latensi_p90_detik": lat[min(len(lat) - 1, int(0.9 * len(lat)))] if lat else 0,
            "latensi_lokal_median_ms": 1000 * statistics.median(h.local_seconds for h in hs) if hs else 0,
            "panggilan_llm": sum(h.llm_called for h in hs),
            "tidak_valid": sum(not h.valid for h in hs),
            "dibuang_kutipan": sum(len(h.dropped_quotes) for h in hs),
            "key_tak_dikenal": sum(len(h.unknown_keys) for h in hs),
        }
    return per_arm


def markdown_report(results: dict, summary: dict, meta: dict, label: dict[str, set[str]], non_base: set[str],
               label_item: dict[str, str]) -> str:
    b = ["# Analisis dampak: aturan vs LLM vs LLM + graf", ""] + [f"- {k}: {v}" for k, v in meta.items()]
    b += ["", "## Kualitas: key yang langsung diatur (dokumen dasar) dan keamanan (fasilitas/prosedural)", "",
          "| lengan | presisi | recall | F1 | set tepat | fasilitas/prosedural diberi key | key palsu |",
          "|---|---|---|---|---|---|---|"]
    for nl in _arms(results):
        r = summary[nl]
        b.append(f"| {nl} | {_pct(r['dasar']['presisi'])} | {_pct(r['dasar']['recall'])} | {_pct(r['dasar']['f1'])} | "
                 f"{r['dasar']['set_tepat']}/{r['dasar']['n']} | {r['bukan_dasar']['dokumen_dengan_key']}/{r['bukan_dasar']['n']} | "
                 f"{r['bukan_dasar']['key_palsu']} |")
    b += ["", "## Biaya dan latensi (per dokumen; latensi LLM diukur saat dipanggil, cache menyimpan angka aslinya)", "",
          "| lengan | panggilan LLM | token masuk | token keluar | biaya total USD | biaya/dokumen USD | latensi median s | p90 s "
          "| non-LLM median ms |",
          "|---|---|---|---|---|---|---|---|---|"]
    for nl in _arms(results):
        r = summary[nl]
        b.append(f"| {nl} | {r['panggilan_llm']}/{len(results)} | {r['token_masuk']:,} | {r['token_keluar']:,} | {r['biaya_usd']:.4f} | "
                 f"{r['biaya_usd_per_dokumen']:.5f} | {r['latensi_median_detik']:.2f} | {r['latensi_p90_detik']:.2f} | "
                 f"{r['latensi_lokal_median_ms']:.1f} |")
    arms = _arms(results)
    ref = "llm_graf" if "llm_graf" in arms else arms[-1]
    llm_arms = [a for a in arms if a != "aturan"]
    b += ["", "Key dibuang karena kutipan tidak ada di teks: "
          + (", ".join(f"{a} {summary[a]['dibuang_kutipan']}" for a in llm_arms) or "-")
          + "; tidak valid: " + (", ".join(f"{a} {summary[a]['tidak_valid']}" for a in llm_arms) or "-") + ".", ""]
    b += ["## Per dokumen", "", "| id | label | benar | " + " | ".join(arms) + f" | turunan dari graf ({ref}) |",
          "|---|---|---|" + "---|" * len(arms) + "---|"]
    ordered = sorted(results, key=lambda i: (i in non_base, i))
    for i in ordered:
        h = results[i]
        expected = ", ".join(sorted(label.get(i, set()))) or "-"
        cols = [", ".join(sorted(h[nl].keys)) or "-" for nl in _arms(results)]
        b.append(f"| `{i}` | {label_item[i]} | {expected} | " + " | ".join(cols)
                 + f" | {', '.join(sorted(h[ref].derived)) or '-'} |")
    b += ["", "## Contoh keluaran graf untuk reviewer (dokumen dasar)", ""]
    for i in ordered:
        h = results[i][ref]
        if i in non_base or not h.keys:
            continue
        b.append(f"- `{i}`: key {sorted(h.keys)}; turunan {sorted(h.derived) or '-'}; "
                 f"{len(h.functions)} fungsi hitung; test: {', '.join(sorted(h.tests)) or '-'}"
                 + (f"; dari relasi teks: {sorted(h.from_relations)}" if h.from_relations else "")
                 + (f"; dibuang (kutipan): {h.dropped_quotes}" if h.dropped_quotes else ""))
    return "\n".join(b) + "\n"


def to_json(results: dict, summary: dict, meta: dict) -> dict:
    return {
        "meta": meta, "ringkas": summary,
        "dokumen": {i: {nl: {"keys": sorted(h[nl].keys), "alasan": h[nl].reasons, "detik": h[nl].seconds,
                             "token_masuk": h[nl].tokens_in, "token_keluar": h[nl].tokens_out,
                             "dibuang_kutipan": h[nl].dropped_quotes, "turunan": sorted(h[nl].derived),
                             "fungsi": sorted(h[nl].functions), "test": sorted(h[nl].tests)} for nl in _arms(results)}
                    for i, h in results.items()},
    }


def console_lines(nl: str, r: dict, n: int) -> str:
    return (f"{nl:16} llm={r['panggilan_llm']}/{n} P={_pct(r['dasar']['presisi'])} R={_pct(r['dasar']['recall'])} "
            f"set_tepat={r['dasar']['set_tepat']}/{r['dasar']['n']} "
            f"fasilitas/prosedural_diberi_key={r['bukan_dasar']['dokumen_dengan_key']}/{r['bukan_dasar']['n']} "
            f"token={r['token_masuk']}+{r['token_keluar']} biaya=${r['biaya_usd']:.4f} "
            f"latensi_median={r['latensi_median_detik']:.2f}s")
