import importlib
import json

import pytest

from taxagent.monitor.classify_llm import LLMCache, LLMClassification
from taxagent.monitor.enrichment import Enrichment
from taxagent.monitor.identity import canon_id
from taxagent.monitor.impact import MeteredClient, build_graph
from taxagent.monitor.review import summarize
from taxagent.monitor.sources import FeedDocument
from taxagent.monitor.storage import MonitorState, load, save
from taxagent.monitor.text import extract

J = importlib.import_module("taxagent.monitor.run")

TEKS_PTKP = (
    "PERATURAN MENTERI KEUANGAN NOMOR 9 TAHUN 2027 TENTANG PENYESUAIAN BESARNYA PENGHASILAN TIDAK KENA PAJAK. "
    "Pasal 1 Penghasilan Tidak Kena Pajak per tahun diberikan paling sedikit sebesar Rp60.000.000,00. "
    "Pasal 2 Pada saat Peraturan Menteri ini mulai berlaku, Peraturan Menteri Keuangan Nomor 101/PMK.010/2016 "
    "tentang Penyesuaian Besarnya Penghasilan Tidak Kena Pajak dicabut dan dinyatakan tidak berlaku. "
    "Pasal 3 Peraturan Menteri ini mulai berlaku pada tanggal diundangkan."
)
TEKS_DTP = (
    "PERATURAN MENTERI KEUANGAN NOMOR 8 TAHUN 2027 TENTANG INSENTIF FISKAL SEKTOR TERTENTU. Pasal 2 Pajak "
    "Penghasilan Pasal 21 yang terutang atas penghasilan pegawai dihitung dengan tarif Pasal 17 ayat (1) huruf a "
    "dan ditanggung pemerintah untuk Masa Pajak Januari sampai dengan Desember 2027."
)
TEKS_BEA = "KEPUTUSAN MENTERI KEUANGAN TENTANG PENETAPAN HARGA EKSPOR UNTUK PENGHITUNGAN BEA KELUAR."

TEKS = {"pmk-9-2027": TEKS_PTKP, "pmk-8-2027": TEKS_DTP, "kmk-7-2027": TEKS_BEA}


def _dok(slug, judul, ident):
    return FeedDocument(id=f"https://jdih.kemenkeu.go.id/dok/{slug}", url="", slug=slug, title=judul,
                        subject="", date="2027-01-02", identity=canon_id(ident))


DOKUMEN = [
    _dok("pmk-9-2027", "PMK 9 TAHUN 2027", "PMK 9 Tahun 2027"),
    _dok("pmk-8-2027", "PMK 8 TAHUN 2027", "PMK 8 Tahun 2027"),
    _dok("kmk-7-2027", "KMK 7 TAHUN 2027", "KMK 7 Tahun 2027"),
]


@pytest.fixture
def perkaya_palsu(monkeypatch):
    def perkaya(slug, ambil, ident, ocr=None):
        t = TEKS[slug]
        return Enrichment(text=extract(t, ident), raw_text=t, text_url=f"https://x/{slug}.pdf")
    monkeypatch.setattr(J, "enrich", perkaya)


def _status():
    return MonitorState(dilihat={"lama": {"first_seen": "2027-01-01T00:00:00"}})


def _penilai(peta, catat=None):
    def nilai(ident, judul, perihal, teks):
        if catat is not None:
            catat.append(ident)
        for kata, kat in peta.items():
            if kata in teks:
                return LLMClassification(kat, f"karena {kata}", "{}", True)
        return LLMClassification("tidak_relevan", "lain", "{}", True)
    return nilai


def test_without_llm_and_graph_old_behaviour(perkaya_palsu):
    h = J.run(DOKUMEN, _status(), fetch=lambda u: b"", now="2027-01-03T08:00:00")
    ids = {c.identitas for c in h.new_notes}
    assert ids == {"PMK 9 Tahun 2027"}
    c = h.new_notes[0]
    assert c.pendapat_llm is None and c.dampak is None and "ptkp" in c.key_terdampak


def test_graph_without_llm_gives_impact_and_derived(perkaya_palsu):
    h = J.run(DOKUMEN, _status(), fetch=lambda u: b"", now="2027-01-03T08:00:00", graph=build_graph())
    c = h.new_notes[0]
    assert c.dampak["sumber"] == "graf" and "ptkp" in c.dampak["keys"]
    assert {"kategori_ter", "ter_bulanan"} <= set(c.dampak["turunan"]) and c.dampak["fungsi"]
    assert any("dampak (graf)" in b for b in J.impact_lines(c))


def test_llm_raises_rule_misses_and_facility_gate(perkaya_palsu):
    catat: list = []
    klien_dipanggil: list = []

    def panggil(sistem, pengguna):
        klien_dipanggil.append(pengguna)
        return {"teks": '{"key": [{"key": "tarif_pasal_17", "kutipan": "dihitung dengan tarif Pasal 17 ayat (1) huruf a"}]}'}

    h = J.run(
        DOKUMEN, _status(), fetch=lambda u: b"", now="2027-01-03T08:00:00",
        llm_judge=_penilai({"ditanggung pemerintah": "fasilitas"}, catat),
        graph=build_graph(), impact_client=MeteredClient(panggil, "tiruan", LLMCache(None)),
    )
    assert len(catat) == 3 and h.llm_called == 3 and h.llm_promoted == 1
    per_id = {c.identitas: c for c in h.new_notes}
    assert set(per_id) == {"PMK 9 Tahun 2027", "PMK 8 Tahun 2027"}
    dtp = per_id["PMK 8 Tahun 2027"]
    assert dtp.kategori == "fasilitas" and dtp.pendapat_llm["kategori"] == "fasilitas"
    assert dtp.dampak["sumber"] == "gerbang_fasilitas" and dtp.key_terdampak == []
    assert per_id["PMK 9 Tahun 2027"].dampak["sumber"] == "gabungan"
    assert "ptkp" in per_id["PMK 9 Tahun 2027"].dampak["keys"]
    assert len(klien_dipanggil) == 1 and "Teks lengkap:" in klien_dipanggil[0]
    assert "masuk review hanya karena LLM" in J.text_report(h)


def test_invalid_llm_does_not_flood_queue_but_warns(perkaya_palsu):
    def rusak(ident, judul, perihal, teks):
        return LLMClassification("perlu_ditinjau", "panggilan LLM gagal: timeout", "", False)

    h = J.run(DOKUMEN, _status(), fetch=lambda u: b"", now="2027-01-03T08:00:00", llm_judge=rusak)
    h.set_code()
    assert {c.identitas for c in h.new_notes} == {"PMK 9 Tahun 2027"}
    assert h.llm_failed == 3 and any("pendapat LLM gagal" in p for p in h.warnings)
    assert h.exit_code == J.CODE_FINDINGS


def test_new_note_saved_and_old_status_still_readable(perkaya_palsu, tmp_path):
    status = _status()
    J.run(DOKUMEN, status, fetch=lambda u: b"", now="2027-01-03T08:00:00",
          llm_judge=_penilai({"ditanggung pemerintah": "fasilitas"}), graph=build_graph())
    berkas = tmp_path / "status.json"
    save(status, berkas)
    ulang = load(berkas)
    assert ulang.catatan[0].dampak and any(c.pendapat_llm for c in ulang.catatan)
    teks_review = "\n".join(summarize(i, c) for i, c in enumerate(ulang.catatan, 1))
    assert "pendapat LLM + teks: fasilitas" in teks_review and "gerbang" in teks_review
    data = json.loads(berkas.read_text(encoding="utf-8"))
    for c in data["catatan"]:
        c.pop("dampak"), c.pop("pendapat_llm")
    berkas.write_text(json.dumps(data), encoding="utf-8")
    assert load(berkas).catatan[0].dampak is None
