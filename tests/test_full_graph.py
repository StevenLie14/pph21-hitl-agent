from __future__ import annotations

import datetime as dt

from taxagent.corpus.full_graph import merge_relations, plan, update, write

VER = [{"dari": "PMK 168 Tahun 2023", "jenis": "mencabut", "ke": "PMK 252 Tahun 2008", "kelas": "tanpa_bukti",
        "dicatat_di": ["halaman_pengubah", "halaman_target"], "tgl_mulai_berlaku": ["2023-12-29"],
        "tgl_efektif": "2024-01-01", "tgl_efektif_sumber": "eksplisit"},
       {"dari": "PMK 9 Tahun 2024", "jenis": "mengubah", "ke": "PMK 1 Tahun 1999", "kelas": "belum_bisa_dicek",
        "dicatat_di": ["halaman_target"], "tgl_mulai_berlaku": []}]
TEMU = [{"dari": "PMK 168 Tahun 2023", "jenis": "mencabut", "ke": "PMK 252 Tahun 2008", "kelas": "eksplisit",
         "kutipan": "... dicabut dan dinyatakan tidak berlaku", "pasal": "Pasal 24", "tgl_efektif": "2024-01-01",
         "tgl_efektif_sumber": "eksplisit"},
        {"dari": "PER-2/PJ/2024", "jenis": "mencabut", "ke": "PER-14/PJ/2013", "kelas": "eksplisit",
         "tgl_efektif": None, "tgl_efektif_sumber": "tidak_terekstrak"}]


def test_merge_jdih_and_text_relations():
    rel = merge_relations(VER, TEMU, {"PER-2/PJ/2024": "2024-01-19"})
    x = rel[("PMK 168 Tahun 2023", "mencabut", "PMK 252 Tahun 2008")]
    assert (x["sumber"], x["bukti"], x["pasal"]) == ("jdih+teks", "eksplisit", "Pasal 24")
    assert rel[("PMK 9 Tahun 2024", "mengubah", "PMK 1 Tahun 1999")]["bukti"] == "belum_dicek"
    y = rel[("PER-2/PJ/2024", "mencabut", "PER-14/PJ/2013")]
    assert (y["sumber"], y["tgl_efektif"], y["tgl_perkiraan"]) == ("teks", None, "2024-01-19")


def test_plan_stub_status_and_interval():
    rel = merge_relations(VER, TEMU, {})
    dok = [{"kunci": "PMK 252 Tahun 2008", "mulai": "2008-12-31"}, {"kunci": "PMK 168 Tahun 2023", "mulai": "2024-01-01"},
           {"kunci": "PER-14/PJ/2013", "label_pajak": "Aktif"}]
    r = plan(dok, rel, [], {"ter_bulanan": {"deskripsi": "TER"}}, [("PMK 168 Tahun 2023", "ter_bulanan", [])],
             {"tanggal": "2026-10-11"}, day=dt.date(2026, 10, 11))
    assert r.regulations["PMK 252 Tahun 2008"]["status_hari_ini"] == "dicabut"
    assert r.regulations["PMK 252 Tahun 2008"]["berhenti_pada"] == "2024-01-01"
    assert r.regulations["PER-14/PJ/2013"]["status_hari_ini"] == "dicabut"
    assert r.regulations["PMK 1 Tahun 1999"]["stub"] and r.regulations["PMK 1 Tahun 1999"]["status_hari_ini"] == "berlaku"
    assert len(r.defines) == 1


class _Klien:
    def __init__(self):
        self.perintah = []

    def run(self, cypher, **p):
        self.perintah.append((cypher, p))

    def query(self, cypher, **p):
        return []


def test_write_per_batch_and_build_nodes():
    rel = merge_relations(VER, TEMU, {})
    r = plan([{"kunci": "PMK 252 Tahun 2008"}], rel,
             [{"id": "PMK 252 Tahun 2008#0", "peraturan": "PMK 252 Tahun 2008", "teks": "x", "teks_cari": "x"}],
             {}, [], {"tanggal": "2026-10-11"})
    k = _Klien()
    jumlah = write(k, r, report=lambda *_: None)
    assert jumlah["relasi"] == 3 and jumlah["potongan"] == 1
    assert any("MENCABUT]" in c for c, _ in k.perintah) and any(c.startswith("CREATE (b:Build)") for c, _ in k.perintah)


def test_update_keeps_graph_and_removes_stale_status_property():
    rel = merge_relations(VER, TEMU, {})
    r = plan([{"kunci": "PMK 252 Tahun 2008"}], rel, [], {}, [], {"tanggal": "2026-10-20"})

    class K(_Klien):
        def query(self, cypher, **p):
            if "keys(p)" in cypher:
                return [{"key": "PMK 252 Tahun 2008", "props": ["key", "in_force_until", "ditambah_ingest"]}]
            return []

    k = K()
    r.regulations["PMK 252 Tahun 2008"].pop("berhenti_pada")
    r.regulations["PER-14/PJ/2013"]["berhenti_pada"] = "2024-01-01"
    jumlah = update(k, r, report=lambda *_: None)
    assert jumlah["properti_dihapus_pada"] == 1
    reg = next(p["baris"] for c, p in k.perintah if c.startswith("UNWIND $baris AS b MERGE (p:Regulation"))
    assert next(b for b in reg if b["key"] == "PMK 252 Tahun 2008")["drop"] == ["in_force_until"]
    assert not any("DETACH DELETE" in c or "Chunk" in c for c, _ in k.perintah)
