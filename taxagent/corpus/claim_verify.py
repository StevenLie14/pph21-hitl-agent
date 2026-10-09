from __future__ import annotations

import json
from dataclasses import dataclass, field

from ..monitor.document_tools import READ_CHARS, DocumentTools
from ..monitor.identity import canon_id
from ..monitor.relation_llm import RELATION_TYPES, Relation, excerpt, fold, verify

PROMPT_VERSION = "klaim-v2-2026-10-19"
MAX_STEPS = 6

_TASK = """\
Anda memeriksa klaim situs JDIH tentang relasi antarperaturan Indonesia. Klaim: dokumen <DARI> <KATA> <KE>. \
Tugas Anda: temukan kalimat di dalam dokumen <DARI> yang MENETAPKAN relasi itu (biasanya di Ketentuan \
Penutup: "... dicabut dan dinyatakan tidak berlaku", atau di judul/pembukaan: "Perubahan atas ...", \
"Beberapa ketentuan dalam ... diubah"). Rujukan di Menimbang/Mengingat dan frasa "sebagaimana telah diubah \
dengan" BUKAN bukti. Bila tidak ada kalimat seperti itu, katakan tidak ada; jangan mengarang.

Jenis relasi: mencabut (seluruhnya), mencabut_sebagian (sebagian pasal/ayat/lampiran), mengubah."""

_ANSWER = """\
Jawaban akhir HANYA JSON: {"ada_bukti": true/false, "jenis": "mencabut|mencabut_sebagian|mengubah", \
"kutipan": "potongan VERBATIM 10-60 kata yang memuat nama peraturan TARGET (<KE>) lengkap dengan nomor dan tahunnya, \
disalin persis tanpa ..."}"""

WINDOW_PROMPT = _TASK + "\n\nAnda diberi cuplikan dokumen di sekitar kata kunci relasi.\n\n" + _ANSWER

SEARCH_PROMPT = _TASK + """

Anda TIDAK diberi teks dokumen; pakai alat di dalam dokumen itu, satu per langkah, paling banyak <LANGKAH> langkah:
- {"aksi": "cari", "kueri": "kata atau frasa"}: posisi kemunculan dan potongan pendek di sekitarnya;
- {"aksi": "baca", "posisi": 12345}: <BACA> karakter teks mulai dari posisi itu;
- {"aksi": "selesai", ...}: jawaban akhir.
Saran: cari nomor peraturan target (mis. "<NOMOR>"), "dicabut", "tidak berlaku", "perubahan atas", lalu baca \
posisi yang menjanjikan untuk menyalin kutipan verbatim.

Setiap langkah jawab HANYA satu JSON. """ + _ANSWER.replace("Jawaban akhir HANYA JSON: ", "Bentuk langkah selesai: ")

_VERB = {"mencabut": "mencabut", "mencabut_sebagian": "mencabut sebagian", "mengubah": "mengubah",
         "memperpanjang": "memperpanjang", "mengatur_lebih_lanjut": "mengatur lebih lanjut",
         "ditetapkan_menjadi": "ditetapkan menjadi"}


@dataclass
class ClaimResult:
    claim: dict
    relation: Relation | None = None
    reason: str = ""
    steps: list[dict] = field(default_factory=list)
    token: int = 0
    answer: dict | None = None


def target_parts(key: str) -> tuple[str, int, int] | None:
    ident = canon_id(key)
    return (ident.kind, ident.number, ident.year) if ident else None


def _fill(prompt: str, claim: dict, **extra) -> str:
    values = {"DARI": claim["dari"], "KATA": _VERB.get(claim["jenis"], claim["jenis"]), "KE": claim["ke"], **extra}
    for k, v in values.items():
        prompt = prompt.replace(f"<{k}>", str(v))
    return prompt


def _tokens(record: dict) -> int:
    return int(record.get("token_masuk", 0)) + int(record.get("token_keluar", 0))


def _check(answer: dict | None, text: str, claim: dict, self_id) -> tuple[Relation | None, str]:
    if not isinstance(answer, dict):
        return None, "jawaban bukan JSON"
    if answer.get("ada_bukti") is not True:
        return None, "LLM: tidak ada bukti"
    want = target_parts(claim["ke"])
    if want is None:
        return None, f"target klaim {claim['ke']} tidak terbaca"
    kind = answer.get("jenis") if answer.get("jenis") in RELATION_TYPES else claim["jenis"]
    r, reason = verify({"jenis": kind, "jenis_peraturan": want[0], "nomor": want[1], "tahun": want[2],
                        "kutipan": answer.get("kutipan", "")}, text, self_id)
    if r is None:
        return None, reason
    issuer = canon_id(claim["ke"]).issuer
    if issuer and r.penerbit and r.penerbit != issuer:
        return None, f"penerbit {r.penerbit} bukan {issuer}"
    if r.jenis not in RELATION_TYPES:
        return None, f"jenis {r.jenis} tidak dikenal"
    return r, ""


def verify_window(claim: dict, text: str, client, self_id=None) -> ClaimResult:
    h = ClaimResult(claim)
    system = _fill(WINDOW_PROMPT, claim)
    data, record = client(system, "Cuplikan:\n" + excerpt(text), PROMPT_VERSION)
    h.token, h.answer = _tokens(record), data
    h.relation, h.reason = _check(data, text, claim, self_id)
    return h


def verify_search(claim: dict, text: str, client, self_id=None, max_steps: int = MAX_STEPS) -> ClaimResult:
    h = ClaimResult(claim)
    tools = DocumentTools(text)
    target = target_parts(claim["ke"])
    system = _fill(SEARCH_PROMPT, claim, LANGKAH=max_steps, BACA=READ_CHARS, NOMOR=target[1] if target else "")
    transcript = [f"Panjang dokumen: {len(tools.text)} karakter. Mulai."]
    for step in range(1, max_steps + 1):
        note = "" if step < max_steps else "\nIni langkah terakhir: jawab dengan aksi selesai."
        data, record = client(system, "\n\n".join(transcript) + note, PROMPT_VERSION)
        h.token += _tokens(record)
        if not isinstance(data, dict):
            h.reason = "jawaban bukan JSON"
            return h
        action = data.get("aksi")
        h.steps.append({k: v for k, v in data.items() if k in ("aksi", "kueri", "posisi")})
        if action == "cari":
            hits = tools.search(data.get("kueri", ""))
            transcript.append(f"Langkah {step}: cari {json.dumps(data.get('kueri'), ensure_ascii=False)}\nHasil: "
                              + (json.dumps(hits, ensure_ascii=False) if hits else "tidak ada"))
        elif action == "baca":
            transcript.append(f"Langkah {step}: baca {data.get('posisi')}\nTeks: {tools.read(data.get('posisi'))}")
        else:
            h.answer = data
            h.relation, h.reason = _check(data, text, claim, self_id)
            return h
    h.reason = "langkah habis tanpa jawaban"
    return h


def finding(claim: dict, r: Relation, arm: str, model_id: str, start_offset: int = 0) -> dict:
    b = r.bukti
    return {"dari": claim["dari"], "jenis": r.jenis, "ke": claim["ke"], "sumber": f"teks_llm_klaim_{arm}",
            "asal": "klaim_tanpa_bukti", "dok_sumber": claim.get("sumber_teks"), "dari_id": claim.get("dari_id"),
            "kelas": "eksplisit", "kutipan": b.klausa if b else r.kutipan, "pasal": b.pasal if b else None,
            "bagian": b.bagian if b else None, "offset": [start_offset + b.mulai, start_offset + b.akhir] if b else None,
            "pasal_terdampak": r.pasal or None, "tgl_efektif": None, "tgl_efektif_sumber": "tidak_terekstrak",
            "jenis_klaim": claim["jenis"], "model": model_id, "prompt": PROMPT_VERSION}


def quote_in_text(quote: str, text: str) -> bool:
    return len(fold(quote)) >= 15 and fold(quote) in fold(text)
