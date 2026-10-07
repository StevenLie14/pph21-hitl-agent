from __future__ import annotations

import copy
import datetime as _dt
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..taxes import get as tax_module
from .extraction import OUT_OF_SCOPE, ExtractionResult, Finding
from .gates import NUMBER_SCOPE, GateContext, GateResult, check_gates, decision
from .manifest import load

DATA_DIR = tax_module().data_dir

IN_SCOPE = NUMBER_SCOPE


class DraftRejected(Exception):
    pass


@dataclass
class Comparison:
    key: str
    status: str
    old: object = None
    new: object = None
    source: list[str] = field(default_factory=list)
    quote: str = ""


@dataclass
class Draft:
    year: int
    base_year: int
    comparisons: list[Comparison]
    mismatches: list[str]
    notes: list[str]
    yaml_text: str | None
    report: str
    gates: list[GateResult] = field(default_factory=list)
    decision: str = ""
    decision_reason: list[str] = field(default_factory=list)

    @property
    def berubah(self) -> list[Comparison]:
        return [p for p in self.comparisons if p.status == "berubah"]


def _merge_values(old, new):
    if isinstance(old, dict) and isinstance(new, dict):
        merged = dict(old)
        merged.update(new)
        return merged
    return new


def base_year_for(year: int) -> int:
    available = [t for t in tax_module().available_years() if t <= year]
    if not available:
        raise ValueError(f"tidak ada tabel tarif sampai tahun {year} sebagai pembanding")
    return max(available)


def compare(results: list[ExtractionResult], base: dict) -> list[Comparison]:
    per_key: dict[str, list[Finding]] = {}
    for h in results:
        for t in h.findings:
            same = next((x for x in per_key.get(t.key, []) if x.source == t.source), None)
            if (same is not None and isinstance(same.value, dict) and isinstance(t.value, dict)
                    and not set(same.value) & set(t.value)):
                same.value = {**same.value, **t.value}
                same.quote = f"{same.quote} || {t.quote}"
                continue
            per_key.setdefault(t.key, []).append(Finding(t.key, t.value, t.quote, t.source))
    out = []
    for key in IN_SCOPE:
        old = base.get(key)
        findings = per_key.get(key, [])
        if not findings:
            out.append(Comparison(key, "tidak_ditemukan", old))
            continue
        values = [_merge_values(old, t.value) for t in findings]
        sources = sorted({t.source for t in findings})
        if any(v != values[0] for v in values[1:]):
            out.append(Comparison(key, "konflik", old, values, sources, findings[0].quote))
            continue
        status = "sama" if values[0] == old else "berubah"
        out.append(Comparison(key, status, old, values[0], sources, findings[0].quote))
    return out


def assemble_draft(year: int, results: list[ExtractionResult], base_year: int | None = None,
                   context: GateContext | None = None, base: dict | None = None) -> Draft:
    base_year = base_year or base_year_for(year)
    base = base if base is not None else tax_module().load_raw(base_year)
    comparisons = compare(results, base)
    mismatches = [x for h in results for x in h.mismatches]
    notes = [x for h in results for x in h.notes]
    changed = [p for p in comparisons if p.status == "berubah"]

    yaml_text = None
    if changed:
        draft = _fill_draft(year, base_year, changed, sorted({s for p in changed for s in p.source}))
        _validate(year, base_year, draft)
        yaml_text = _header(year, base_year) + yaml.safe_dump(draft, sort_keys=False, allow_unicode=True, width=100)
    d = Draft(year, base_year, comparisons, mismatches, notes, yaml_text, "")
    d.gates = check_gates(d, results, context)
    d.decision, d.decision_reason = decision(d, d.gates)
    d.report = _report(d)
    return d


def _fill_draft(year: int, base_year: int, changed: list[Comparison], sources: list[str]) -> dict:
    draft_meta = {
        "terverifikasi": False,
        "draf": {
            "dibuat": _dt.date.today().isoformat(),
            "sumber": sources,
            "key_berubah": [p.key for p in changed],
        },
    }
    if base_year < year:
        content = {"meta": {"tahun_pajak": year, "berlaku_sejak": f"{year}-01-01", "warisi_dari": base_year, **draft_meta}}
    else:
        with open(DATA_DIR / f"tarif_{year}.yaml", encoding="utf-8") as f:
            content = copy.deepcopy(yaml.safe_load(f))
        content["meta"] = {**content["meta"], **draft_meta}
    for p in changed:
        content[p.key] = p.new
    return content


def _validate(year: int, base_year: int, draft: dict) -> None:
    parent_year = draft["meta"].get("warisi_dari")
    if parent_year is not None and parent_year != year:
        parent = tax_module().load_raw(int(parent_year))
        merged = dict(parent)
        for k, v in draft.items():
            merged[k] = {**parent.get("meta", {}), **v} if k == "meta" else v
    else:
        merged = draft
    tax_module().validate_rates(merged)
    bracket_keys = [k for k, g in load().groups.items() if any(c["jenis"] == "lapisan_naik" for c in g.consistency)]
    for key in bracket_keys:
        table = merged[key] if isinstance(merged[key], dict) else {"": merged[key]}
        for category, content in table.items():
            limits = [r["batas_atas"] for r in content]
            if limits[-1] is not None or any(a >= b for a, b in zip(limits[:-1], limits[1:-1])):
                raise ValueError(f"draf {key}{f' {category}' if category else ''}: batas lapisan tidak naik atau lapisan "
                                 "teratas tidak terbuka")


def _header(year: int, base_year: int) -> str:
    return (
        f"# DRAF tabel tarif tahun pajak {year}, disusun otomatis oleh `pph21 draft-rates`.\n"
        "#\n"
        "# BELUM BERLAKU. Berkas ini sengaja tidak berada di taxagent/taxes/pph21/data/ dan bernama\n"
        "# draf_tarif_*.yaml sehingga tidak pernah dimuat mesin hitung. Hanya key yang\n"
        f"# berubah terhadap tabel {base_year} yang ditulis; laporan .md di sebelahnya\n"
        "# memuat diff, kutipan pasal, dan key yang tidak terbaca. Untuk memakainya:\n"
        "# cocokkan setiap angka dengan teks resmi, salin manual ke\n"
        f"# taxagent/taxes/pph21/data/tarif_{year}.yaml, lalu `pph21 verify --year {year} --konfirmasi`.\n"
    )


def _fmt(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, list):
        return "; ".join(
            f"s.d. {r['batas_atas']:,}: {r['persen']}%" if r.get("batas_atas") is not None else f"di atasnya: {r['persen']}%"
            for r in v
        )
    if isinstance(v, dict):
        return ", ".join(f"{k}={x:,}" if isinstance(x, (int, float)) else f"{k}={x}" for k, x in v.items())
    return str(v)


def _short(text: str, limit: int = 600) -> str:
    return text if len(text) <= limit else text[:limit] + f" ... ({len(text):,} karakter)"


def _report(d: Draft) -> str:
    lines = [
        f"# Draf tarif {d.year} (pembanding: tabel {d.base_year})",
        "",
        f"Dibuat {_dt.date.today().isoformat()} oleh `pph21 draft-rates`. "
        + (f"**{len(d.berubah)} key berubah**, draf YAML ditulis." if d.berubah else "Tidak ada key yang berubah; draf YAML tidak ditulis."),
        "",
        "| key | status | tabel lama | hasil ekstraksi | sumber |",
        "|---|---|---|---|---|",
    ]
    for p in d.comparisons:
        new = "; ".join(_fmt(v) for v in p.new) if p.status == "konflik" else _fmt(p.new)
        lines.append(f"| `{p.key}` | **{p.status}** | {_fmt(p.old)} | {new} | {', '.join(p.source) or '-'} |")
    if d.decision != "tidak_ada_perubahan":
        label = {True: "lolos", False: "**gagal**", None: "belum dijalankan"}
        lines += [
            "",
            f"## Gerbang: **{d.decision}**",
            "",
            "Draf tetap draf. `siap` = semua gerbang lolos (kandidat penerapan otomatis); "
            "`tahan` = manusia wajib membaca alasan di bawah.",
            "",
            "| gerbang | hasil | alasan |",
            "|---|---|---|",
        ]
        lines += [f"| {g.code} {g.name} | {label[g.passed]} | {'; '.join(g.reasons) or '-'} |" for g in d.gates]
    kutipan = [p for p in d.comparisons if p.quote and p.status in ("berubah", "konflik")]
    if kutipan:
        lines += ["", "## Kutipan pasal", ""] + [f"- `{p.key}`: \"{_short(p.quote)}\"" for p in kutipan]
    if d.mismatches:
        lines += ["", "## Angka tidak dipakai (digit tidak cocok dengan terbilang)", ""] + [f"- {x}" for x in d.mismatches]
    if d.notes:
        lines += ["", "## Catatan ekstraksi", ""] + [f"- {x}" for x in d.notes]
    lines += ["", "## Di luar cakupan ekstraksi otomatis (periksa manual)", ""]
    lines += [f"- `{k}`: {v}" for k, v in OUT_OF_SCOPE.items()]
    lines += [
        "",
        "Status: `berubah` = angka di teks berbeda dari tabel lama; `sama` = terbaca dan identik; "
        "`konflik` = sumber-sumber memberi angka berbeda (tidak dimasukkan ke draf); "
        "`tidak_ditemukan` = pola pasal tidak ada di sumber (bukan berarti tidak berubah).",
    ]
    return "\n".join(lines) + "\n"


def write_draft(d: Draft, folder: Path) -> list[Path]:
    folder = Path(folder).resolve()
    data = DATA_DIR.resolve()
    if folder == data or data in folder.parents:
        raise DraftRejected(f"folder keluaran {folder} berada di dalam {data}; draf tidak boleh ditulis ke data resmi")
    targets = [folder / f"draf_tarif_{d.year}.md"]
    if d.yaml_text is not None:
        targets.append(folder / f"draf_tarif_{d.year}.yaml")
    existing = [p for p in targets if p.exists()]
    if existing:
        raise DraftRejected(f"sudah ada, tidak ditimpa: {', '.join(str(p) for p in existing)}")
    folder.mkdir(parents=True, exist_ok=True)
    for p, content in zip(targets, (d.report, d.yaml_text)):
        with open(p, "x", encoding="utf-8") as f:
            f.write(content)
    return targets
