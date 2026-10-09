from __future__ import annotations

import json

from taxagent.corpus import claim_verify as C

TEKS = ("PERATURAN MENTERI KEUANGAN NOMOR 5 TAHUN 2020 TENTANG X. Menimbang: a. bahwa Peraturan Menteri Keuangan "
        "Nomor 9 Tahun 2018 perlu diganti; Mengingat: 1. Undang-Undang Nomor 7 Tahun 1983; MEMUTUSKAN: Menetapkan: "
        "PERATURAN MENTERI KEUANGAN TENTANG X. Pasal 1 Isi pasal satu tentang pemotongan pajak. " + "isi lain. " * 400 +
        "Pasal 12 Pada saat Peraturan Menteri ini mulai berlaku, Peraturan Menteri Keuangan Nomor 9 Tahun 2018 "
        "tentang X Lama dicabut dan dinyatakan tidak berlaku. Pasal 13 Peraturan Menteri ini mulai berlaku pada "
        "tanggal diundangkan.")
KLAIM = {"dari": "PMK 5 Tahun 2020", "jenis": "mencabut", "ke": "PMK 9 Tahun 2018", "dari_id": "x", "sumber_teks": "jdih"}
KUTIPAN = "Peraturan Menteri Keuangan Nomor 9 Tahun 2018 tentang X Lama dicabut dan dinyatakan tidak berlaku"


class Klien:
    def __init__(self, jawaban):
        self.jawaban, self.pesan = list(jawaban), []

    def __call__(self, system, user, versi):
        self.pesan.append((system, user))
        return self.jawaban.pop(0), {"token_masuk": 100, "token_keluar": 10}


def test_window_arm_verified_by_code_with_target_from_the_claim():
    k = Klien([{"ada_bukti": True, "jenis": "mencabut", "nomor": "5", "tahun": "2020", "kutipan": KUTIPAN}])
    h = C.verify_window(KLAIM, TEKS, k, ("PMK", 5, 2020))
    assert h.relation is not None and h.relation.jenis == "mencabut" and h.relation.bukti.bagian == "batang_tubuh"
    assert h.token == 110 and "PMK 9 Tahun 2018" in k.pesan[0][0]
    t = C.finding(KLAIM, h.relation, "window", "uji")
    assert t["kelas"] == "eksplisit" and t["sumber"] == "teks_llm_klaim_window" and t["ke"] == "PMK 9 Tahun 2018"


def test_invented_or_preamble_quotes_are_rejected():
    palsu = {"ada_bukti": True, "jenis": "mencabut",
             "kutipan": "Peraturan Menteri Keuangan Nomor 9 Tahun 2018 dicabut seluruhnya oleh peraturan ini"}
    assert "tidak ada di teks" in C.verify_window(KLAIM, TEKS, Klien([palsu]), ("PMK", 5, 2020)).reason
    menimbang = {"ada_bukti": True, "jenis": "mencabut", "kutipan": "bahwa Peraturan Menteri Keuangan Nomor 9 Tahun 2018 perlu diganti"}
    assert C.verify_window(KLAIM, TEKS, Klien([menimbang]), ("PMK", 5, 2020)).relation is None
    assert C.verify_window(KLAIM, TEKS, Klien([{"ada_bukti": False}]), None).reason == "LLM: tidak ada bukti"
    lain = {**KLAIM, "ke": "PMK 10 Tahun 2018"}
    assert C.verify_window(lain, TEKS, Klien([{"ada_bukti": True, "kutipan": KUTIPAN}]), None).relation is None


def test_search_arm_tools_and_step_limit():
    alat = C.DocumentTools(TEKS)
    hasil = alat.search("dicabut dan dinyatakan")
    assert hasil and "dicabut" in hasil[-1]["potongan"]
    assert alat.read(hasil[-1]["posisi"]).startswith("dicabut")
    assert alat.search("nomor 9 tahun 2018 lama")
    k = Klien([{"aksi": "cari", "kueri": "Nomor 9 Tahun 2018"}, {"aksi": "baca", "posisi": hasil[-1]["posisi"] - 150},
               {"aksi": "selesai", "ada_bukti": True, "jenis": "mencabut", "kutipan": KUTIPAN}])
    h = C.verify_search(KLAIM, TEKS, k, ("PMK", 5, 2020))
    assert h.relation is not None and [s["aksi"] for s in h.steps] == ["cari", "baca", "selesai"] and h.token == 330
    assert "Hasil:" in k.pesan[1][1] and "Teks:" in k.pesan[2][1]
    terus = Klien([{"aksi": "cari", "kueri": "x"}] * 3)
    h = C.verify_search(KLAIM, TEKS, terus, None, max_steps=3)
    assert h.relation is None and h.reason == "langkah habis tanpa jawaban" and "langkah terakhir" in terus.pesan[-1][1]
    assert json.dumps(C._fill(C.SEARCH_PROMPT, KLAIM, LANGKAH=3, BACA=10, NOMOR=9)).count("<") == 0
