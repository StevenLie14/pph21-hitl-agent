from __future__ import annotations

import copy
import datetime as dt
import hashlib
import html
import json
import random
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml

from ..taxes import get as tax_module
from .llm import leaves

DATA_DIR = tax_module().data_dir

VERSION = 1


def _number(v):
    return None if v is None else (int(v) if Decimal(str(v)) == int(Decimal(str(v))) else float(v))


def save_json(d, folder: Path, meta: dict | None = None) -> Path:
    folder = Path(folder)
    f = folder / f"draf_tarif_{d.year}.json"
    content = {
        "versi": VERSION, "tahun": d.year, "tahun_dasar": d.base_year, "dibuat": dt.date.today().isoformat(),
        "keputusan_gerbang": d.decision, "alasan_keputusan": d.decision_reason, "meta": meta or {},
        "perbandingan": [{"key": p.key, "status": p.status, "lama": p.old, "baru": p.new, "sumber": p.source,
                          "kutipan": p.quote} for p in d.comparisons],
        "gerbang": [{"kode": g.code, "nama": g.name, "lolos": g.passed, "alasan": g.reasons} for g in d.gates],
        "tidak_cocok": d.mismatches, "catatan": d.notes,
    }
    with open(f, "x", encoding="utf-8") as h:
        json.dump(content, h, ensure_ascii=False, indent=1, default=str)
    return f


def cards(draft: dict) -> list[dict]:
    card_out = []
    for p in draft["perbandingan"]:
        if p["status"] != "berubah":
            continue
        old, new = leaves(p["lama"], p["key"]), leaves(p["baru"], p["key"])
        changed = [{"jalur": j, "lama": _number(old.get(j)), "baru": _number(v)}
                   for j, v in new.items() if old.get(j) != v]
        unchanged = [{"jalur": j, "nilai": _number(v)} for j, v in new.items() if old.get(j) == v]
        card_out.append({"id": p["key"], "key": p["key"], "kutipan": p["kutipan"], "sumber": p["sumber"],
                      "berubah": changed, "tetap": unchanged, "baru": p["baru"]})
    return card_out


def embed_data(card_list: list[dict], n: int, seed: int) -> tuple[list[dict], list[dict]]:
    rng = random.Random(seed)
    answer_key, extra = [], []
    candidates = [k for k in card_list if any(b["baru"] for b in k["berubah"])]
    for i in range(min(n, len(candidates) * 3)):
        k = copy.deepcopy(rng.choice(candidates))
        b = rng.choice([x for x in k["berubah"] if x["baru"]])
        method = rng.choice(["x10", "kurang_digit", "tambah_5persen"])
        v = Decimal(str(b["baru"]))
        wrong = v * 10 if method == "x10" else (v / 10 if method == "kurang_digit" else v * Decimal("1.05"))
        wrong = _number(wrong.quantize(Decimal("0.01")) if wrong != int(wrong) else int(wrong))
        k["id"] = hashlib.sha1(f"{seed}-{i}-{k['key']}".encode()).hexdigest()[:10]
        b["baru"] = wrong
        extra.append(k)
        answer_key.append({"id": k["id"], "key": k["key"], "jalur": b["jalur"], "benar": _number(v), "draf_salah": wrong,
                      "cara": method})
    all_cards = card_list + extra
    rng.shuffle(all_cards)
    return all_cards, answer_key


_CSS = """
:root{--bg:#f6f7f6;--surface:#fff;--fg:#1d2523;--muted:#5b6965;--line:#d6dcda;--accent:#0d6b5f;--ok:#2f7d32;
--warn:#9a6400;--bad:#b3261e}
@media (prefers-color-scheme:dark){:root{--bg:#121716;--surface:#1a2120;--fg:#e3e9e7;--muted:#9aa8a4;--line:#2e3836;
--accent:#5cc4b3;--ok:#7cc47f;--warn:#e3b25a;--bad:#f08a80;color-scheme:dark}}
*{box-sizing:border-box}body{background:var(--bg);color:var(--fg);font:15px/1.6 system-ui,sans-serif;margin:0}
.wrap{max-width:900px;margin:0 auto;padding:24px 16px 80px;display:grid;gap:18px}
h1{font-size:1.5rem;margin:0}.muted{color:var(--muted)}code{font-family:ui-monospace,Consolas,monospace;font-size:.88em}
.kartu{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:16px;display:grid;gap:12px}
.kartu.selesai{border-left:4px solid var(--accent)}blockquote{margin:0;padding:8px 12px;border-left:3px solid var(--line);
white-space:pre-wrap;max-height:260px;overflow:auto}
table{border-collapse:collapse;width:100%}td,th{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;
vertical-align:top}th{font-size:.75rem;text-transform:uppercase;color:var(--muted)}
input[type=text]{font:inherit;padding:4px 8px;width:100%;max-width:220px;border:1px solid var(--line);border-radius:4px;
background:var(--bg);color:var(--fg)}textarea{font:inherit;width:100%;min-height:52px;border:1px solid var(--line);
border-radius:4px;background:var(--bg);color:var(--fg);padding:6px}
button{font:inherit;padding:6px 14px;border-radius:6px;border:1px solid var(--line);background:var(--bg);color:var(--fg);
cursor:pointer}button[disabled]{opacity:.4;cursor:not-allowed}button.pilih{outline:2px solid var(--accent)}
.draf{display:none}.terbuka .draf{display:table-cell}.cocok{color:var(--ok)}.beda{color:var(--bad);font-weight:600}
.gerbang li.gagal{color:var(--bad)}.bar{position:sticky;bottom:0;background:var(--surface);border-top:1px solid var(--line);
padding:10px 16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;justify-content:center}
"""

_JS = """
const DATA = JSON.parse(document.getElementById('data').textContent);
const keputusan = {};
const KOSONG = ['-', 'kosong', 'null', 'tidak ada'];
function normal(s){ s=(s||'').trim(); if(KOSONG.includes(s.toLowerCase())) return null;
  s=s.replace(/^rp\\s*/i,'').replace(/%$/,'').replace(/\\s/g,'');
  if(s==='') return null; if(/^\\d{1,3}(\\.\\d{3})+(,\\d+)?$/.test(s)) s=s.replace(/\\./g,'').replace(',','.');
  else s=s.replace(',','.'); const n=Number(s); return isNaN(n)?NaN:n; }
function cek(id){
  const k=document.getElementById('k-'+id), d=DATA.kartu.find(x=>x.id===id);
  const isian=[...k.querySelectorAll('input[data-jalur]')];
  const semua=isian.every(i=>i.value.trim()!=='');
  k.classList.toggle('terbuka', semua);
  let sama=true;
  isian.forEach((i,n)=>{ const v=normal(i.value), b=d.berubah[n].baru;
    const ok=b===null ? v===null : (v!==null && Math.abs(v-b)<1e-9);
    const sel=k.querySelector('[data-hasil="'+n+'"]'); sel.textContent=semua?(ok?'sama':'BEDA'):'';
    sel.className=semua?(ok?'cocok':'beda'):''; if(!ok) sama=false; });
  k.querySelector('.terima').disabled=!(semua&&sama);
  k.querySelector('.tolak').disabled=!semua; k.querySelector('.tahan').disabled=!semua;
}
function putuskan(id, nilai){
  const k=document.getElementById('k-'+id);
  const cat=k.querySelector('textarea').value.trim();
  if(nilai!=='terima' && !cat){ k.querySelector('textarea').focus(); k.querySelector('.wajib').hidden=false; return; }
  keputusan[id]={keputusan:nilai, catatan:cat, waktu:new Date().toISOString(),
    isian:Object.fromEntries([...k.querySelectorAll('input[data-jalur]')].map(i=>[i.dataset.jalur,i.value.trim()]))};
  k.querySelectorAll('.aksi button').forEach(b=>b.classList.toggle('pilih', b.classList.contains(nilai)));
  k.classList.add('selesai'); k.querySelector('.wajib').hidden=true; hitung();
}
function hitung(){ const n=Object.keys(keputusan).length; document.getElementById('jumlah').textContent=
  n+' / '+DATA.kartu.length+' kartu diputuskan'; document.getElementById('ekspor').disabled=n===0; }
function ekspor(){
  const nama=document.getElementById('reviewer').value.trim();
  if(!nama){ document.getElementById('reviewer').focus(); return; }
  const isi={versi:DATA.versi, tahun:DATA.tahun, sidik_draf:DATA.sidik, reviewer:nama,
    diekspor:new Date().toISOString(), keputusan};
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([JSON.stringify(isi,null,1)],{type:'application/json'}));
  a.download='keputusan_review_'+DATA.tahun+'.json'; a.click();
}
document.querySelectorAll('input[data-jalur]').forEach(i=>i.addEventListener('input',()=>cek(i.dataset.kartu)));
hitung();
"""


INSERT_METHODS = ("x10", "kurang_digit", "tambah_5persen", "salah_konteks")


def _wrong_number(v: Decimal, method: str):
    wrong = v * 10 if method == "x10" else (v / 10 if method == "kurang_digit" else v * Decimal("1.05"))
    return _number(wrong.quantize(Decimal("0.01")) if wrong != int(wrong) else int(wrong))


def insert_per_key(card_list: list[dict], n: int, seed: int) -> tuple[list[dict], list[dict]]:
    rng = random.Random(seed)
    result = copy.deepcopy(card_list)
    for i, k in enumerate(result):
        k["id"] = hashlib.sha1(f"{seed}-{i}-{k['key']}".encode()).hexdigest()[:10]
    answer_key = []
    candidates = [k for k in result if any(b["baru"] for b in k["berubah"])]
    for k in rng.sample(candidates, min(n, len(candidates))):
        others = [x for x in card_list if x["key"] != k["key"] and x["kutipan"] and x["kutipan"] != k["kutipan"]]
        method = rng.choice(INSERT_METHODS if others else INSERT_METHODS[:3])
        if method == "salah_konteks":
            source = rng.choice(others)
            k["kutipan"], k["sumber"] = source["kutipan"], source["sumber"]
            answer_key.append({"id": k["id"], "key": k["key"], "jalur": None, "benar": None, "draf_salah": None,
                               "cara": method, "kutipan_dari": source["key"]})
            continue
        b = rng.choice([x for x in k["berubah"] if x["baru"]])
        right = _number(Decimal(str(b["baru"])))
        b["baru"] = _wrong_number(Decimal(str(b["baru"])), method)
        answer_key.append({"id": k["id"], "key": k["key"], "jalur": b["jalur"], "benar": right, "draf_salah": b["baru"],
                           "cara": method})
    rng.shuffle(result)
    return result, answer_key


def _same_shape(old, new) -> bool:
    if isinstance(old, dict):
        return isinstance(new, dict) and set(old) == set(new) and all(_same_shape(old[k], new[k]) for k in old)
    if isinstance(old, list):
        return isinstance(new, list) and bool(new) and all(_same_shape(old[0], x) for x in new) if old else \
            isinstance(new, list)
    if old is None or new is None:
        return True
    return isinstance(new, (int, float)) and not isinstance(new, bool) if isinstance(old, (int, float)) else \
        type(old) is type(new)


def manual_value(key: str, text: str, base_table: dict, card_keys: set[str]) -> object:
    if key in card_keys:
        raise ValueError(f"{key} sudah ada kartunya; putuskan lewat kartu itu")
    if key not in base_table:
        raise ValueError(f"key {key} tidak ada di tabel tahun dasar")
    try:
        value = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ValueError(f"nilai {key} bukan YAML/JSON yang sah: {e}") from e
    if not _same_shape(base_table[key], value):
        raise ValueError(f"bentuk nilai {key} tidak sama dengan tabel tahun dasar")
    if value == base_table[key]:
        raise ValueError(f"nilai {key} sama dengan tabel tahun dasar")
    return value


def _fmt(v) -> str:
    if v is None:
        return "(kosong)"
    if isinstance(v, (int, float)):
        return f"{v:,}".replace(",", ".") if isinstance(v, int) else str(v)
    return html.escape(json.dumps(v, ensure_ascii=False))


def draft_fingerprint(draft: dict) -> str:
    return hashlib.sha1(json.dumps(draft, sort_keys=True, default=str).encode()).hexdigest()[:12]


def render_page(draft: dict, card_list: list[dict]) -> str:
    fingerprint = draft_fingerprint(draft)
    meta = draft.get("meta") or {}
    gates_html = "".join(
        f'<li class="{"gagal" if g["lolos"] is False else ""}"><b>{html.escape(g["kode"])}</b> {html.escape(g["nama"])}: '
        f'{ {True: "lolos", False: "GAGAL", None: "tidak dijalankan"}[g["lolos"]]}'
        f'{" (" + html.escape("; ".join(g["alasan"])) + ")" if g["alasan"] else ""}</li>' for g in draft["gerbang"])
    cards_html = []
    for k in card_list:
        rows = "".join(
            f'<tr><td><code>{html.escape(b["jalur"])}</code></td><td>{_fmt(b["lama"])}</td>'
            f'<td><input type="text" inputmode="decimal" data-kartu="{k["id"]}" data-jalur="{html.escape(b["jalur"])}" '
            f'aria-label="nilai baru {html.escape(b["jalur"])} menurut Anda"></td>'
            f'<td class="draf">{_fmt(b["baru"])}</td><td class="draf"><span data-hasil="{n}"></span></td></tr>'
            for n, b in enumerate(k["berubah"]))
        unchanged = (f'<details><summary class="muted">{len(k["tetap"])} angka lain di key ini tidak berubah</summary>'
                 + "".join(f'<div><code>{html.escape(t["jalur"])}</code> = {_fmt(t["nilai"])}</div>' for t in k["tetap"])
                 + "</details>") if k["tetap"] else ""
        cards_html.append(f"""
<section class="kartu" id="k-{k['id']}">
  <div><b><code>{html.escape(k['key'])}</code></b> <span class="muted">sumber: {html.escape(', '.join(k['sumber']))}</span></div>
  <blockquote>{html.escape(k['kutipan'] or '(tidak ada kutipan; baca teks sumber)')}</blockquote>
  <div class="muted">1) Baca kutipan, isi angka baru menurut Anda. Angka draf muncul setelah semua isian terisi.</div>
  <table><thead><tr><th>angka</th><th>tabel lama</th><th>menurut Anda</th><th class="draf">draf sistem</th>
  <th class="draf">cocok?</th></tr></thead><tbody>{rows}</tbody></table>
  {unchanged}
  <textarea placeholder="Catatan (wajib untuk tolak/tahan)"></textarea>
  <div class="wajib muted" hidden>Tulis alasan dulu.</div>
  <div class="aksi"><button class="terima" disabled onclick="putuskan('{k['id']}','terima')">Terima</button>
  <button class="tolak" disabled onclick="putuskan('{k['id']}','tolak')">Tolak</button>
  <button class="tahan" disabled onclick="putuskan('{k['id']}','tahan')">Tahan</button></div>
</section>""")
    data = {"versi": VERSION, "tahun": draft["tahun"], "sidik": fingerprint,
            "kartu": [{"id": k["id"], "berubah": [{"jalur": b["jalur"], "baru": b["baru"]} for b in k["berubah"]]}
                      for k in card_list]}
    source = ", ".join(html.escape(str(x)) for x in [meta.get("identitas"), meta.get("url_teks")] if x)
    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html><html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Review tarif {draft['tahun']}</title>
<style>{_CSS}</style></head><body><div class="wrap">
<h1>Review draf tarif {draft['tahun']}</h1>
<div class="muted">Pembanding: tabel {draft['tahun_dasar']}. Peraturan: {source or '-'}. Keputusan gerbang:
<b>{html.escape(draft['keputusan_gerbang'])}</b>. Sidik draf <code>{fingerprint}</code>.</div>
<details><summary>Hasil gerbang G1-G8</summary><ul class="gerbang">{gates_html}</ul></details>
<p>Setiap kartu: isi angka menurut Anda dari kutipan pasal, baru angka draf terlihat. <b>Terima</b> hanya aktif bila
semua isian sama dengan draf. Keputusan diekspor ke JSON lalu diproses <code>pph21 review-draft --decision</code>;
halaman ini tidak mengubah tabel tarif.</p>
{''.join(cards_html)}
<script type="application/json" id="data">{data_json}</script>
</div><div class="bar"><label>Reviewer <input type="text" id="reviewer" placeholder="nama"></label>
<span id="jumlah" class="muted"></span><button id="ekspor" disabled onclick="ekspor()">Ekspor keputusan</button></div>
<script>{_JS}</script></body></html>
"""


_EMPTY = ("-", "kosong", "null", "tidak ada")


def _input_value(s: str):
    s = (s or "").strip().lower()
    if s in _EMPTY:
        return "kosong"
    s = s.removeprefix("rp").strip().rstrip("%").replace(" ", "")
    if not s:
        return None
    if "." in s and "," not in s and all(len(x) == 3 for x in s.split(".")[1:]):
        s = s.replace(".", "")
    elif "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def apply_decisions(draft: dict, card_list: list[dict], decisions: dict, inserted_key: list[dict] | None = None
                     ) -> tuple[dict, list[dict], dict]:
    inserted = {x["id"]: x for x in (inserted_key or [])}
    per_id = {k["id"]: k for k in card_list}
    patch, log = {}, []
    summary = {"kartu": len(card_list), "diputuskan": 0, "diterima": 0, "ditolak": 0, "ditahan": 0, "ditolak_sistem": 0,
               "sisipan": len(inserted), "sisipan_tertangkap": 0, "sisipan_lolos": 0, "belum_diputuskan": []}
    for kid, k in per_id.items():
        dec = (decisions.get("keputusan") or {}).get(kid)
        if dec is None:
            summary["belum_diputuskan"].append(k["key"])
            continue
        summary["diputuskan"] += 1
        different = [b["jalur"] for b in k["berubah"]
                if _input_value(dec.get("isian", {}).get(b["jalur"], ""))
                != ("kosong" if b["baru"] is None else Decimal(str(b["baru"])))]
        verdict = dec["keputusan"]
        note = dec.get("catatan", "")
        if verdict == "terima" and different:
            verdict, note = "ditolak_sistem", f"isian reviewer berbeda dari draf: {', '.join(different)}"
        if kid in inserted:
            caught = verdict != "terima"
            summary["sisipan_tertangkap" if caught else "sisipan_lolos"] += 1
            log.append({"id": kid, "key": k["key"], "sisipan": True, "keputusan": verdict, "tertangkap": caught,
                        **{x: inserted[kid][x] for x in ("jalur", "benar", "draf_salah", "cara")}})
            continue
        summary[{"terima": "diterima", "tolak": "ditolak", "tahan": "ditahan"}.get(verdict, "ditolak_sistem")] += 1
        if verdict == "terima":
            patch[k["key"]] = k["baru"]
        log.append({"id": kid, "key": k["key"], "keputusan": verdict, "catatan": note, "isian": dec.get("isian"),
                    "waktu": dec.get("waktu")})
    return patch, log, summary


def write_patch(draft: dict, patch: dict, log: list[dict], summary: dict, reviewer: str, folder: Path,
                manual: list[str] | None = None) -> list[Path]:
    folder = Path(folder).resolve()
    data = DATA_DIR.resolve()
    if folder == data or data in folder.parents:
        raise ValueError(f"folder {folder} berada di dalam {data}; patch tidak boleh ditulis ke data resmi")
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    if patch:
        f = folder / f"patch_tarif_{draft['tahun']}.yaml"
        header = (f"# Patch hasil review manusia ({reviewer}, {dt.date.today().isoformat()}): key yang DITERIMA saja.\n"
                  f"# Salin manual ke taxagent/taxes/pph21/data/tarif_{draft['tahun']}.yaml, lalu: pph21 verify --year "
                  f"{draft['tahun']} --konfirmasi\n")
        if manual:
            header += (f"# DITAMBAHKAN MANUAL oleh reviewer (tidak lewat ekstraktor dan gerbang G1-G8): "
                       f"{', '.join(manual)}\n")
        with open(f, "x", encoding="utf-8") as h:
            identity = (draft.get("meta") or {}).get("identitas")
            content = dict(patch)
            if identity:
                content = {"meta": {"dasar_hukum_kunci": {k.split(".")[0].split("[")[0]: str(identity) for k in patch}},
                           **content}
            h.write(header + yaml.safe_dump(content, allow_unicode=True, sort_keys=False))
        out.append(f)
    f = folder / f"review_tarif_{draft['tahun']}.jsonl"
    with open(f, "a", encoding="utf-8") as h:
        h.write(json.dumps({"reviewer": reviewer, "waktu": dt.datetime.now().isoformat(timespec="seconds"),
                            "ringkas": summary, "kartu": log}, ensure_ascii=False, default=str) + "\n")
    out.append(f)
    return out
