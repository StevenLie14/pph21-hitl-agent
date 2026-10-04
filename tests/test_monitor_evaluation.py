from __future__ import annotations

import json

import pytest

from taxagent.monitor import ImpactNote
from taxagent.monitor.classify import load_watchlist
from taxagent.monitor.evaluation import (
    LABELS,
    EvalItem,
    Prediction,
    SetResult,
    enrichment_stats,
    evaluate,
    load_set,
    score_set,
    status_latency,
    wilson,
)


def test_wilson_interval():
    lo, hi = wilson(33, 35)
    assert 0.80 < lo < 0.82 and 0.98 < hi < 0.99
    assert wilson(0, 0) == (0.0, 0.0)
    assert wilson(16, 16)[1] == 1.0


def _hasil(pasangan) -> SetResult:
    h = SetResult("uji")
    for label, prediksi in pasangan:
        h.predictions.append(Prediction(EvalItem("uji", "x", "x", label), prediksi, []))
    return h


def test_binary_score_counts_needs_review_as_positive():
    h = _hasil([
        ("dasar", "dasar"), ("fasilitas", "perlu_ditinjau"), ("prosedural", "tidak_relevan"),
        ("tidak_relevan", "prosedural"), ("tidak_relevan", "tidak_relevan"),
    ])
    s = h.binary()
    assert (s.tp, s.fp, s.fn, s.tn) == (2, 1, 1, 1)
    kat = h.per_category()
    assert (kat["fasilitas"].tp, kat["fasilitas"].fn) == (0, 1)
    assert h.confusion()["fasilitas"]["perlu_ditinjau"] == 1
    assert [p.item.label for p in h.salah] == ["prosedural", "tidak_relevan"]


def test_labelled_set_valid():
    sets = load_set()
    assert set(sets) == {"kurasi", "feed", "pajakgoid"}
    assert len(sets["feed"]) == 98 and all(i.label == "tidak_relevan" for i in sets["feed"])
    for items in sets.values():
        assert all(i.label in LABELS for i in items)
        ids = [i.id for i in items]
        assert len(ids) == len(set(ids))
    assert sum(i.label != "tidak_relevan" for i in sets["pajakgoid"]) == 41


def test_classifier_metrics_regression():
    h = evaluate()
    k, f, p = h["kurasi"].binary(), h["feed"].binary(), h["pajakgoid"].binary()
    assert (k.tp, k.fp, k.fn) == (16, 0, 0)
    assert (f.tp, f.fp) == (0, 0)
    assert (p.tp, p.fp, p.fn) == (36, 45, 5)
    assert {x.item.id for x in h["pajakgoid"].salah if x.label_is_positive} == {"PMK 81 Tahun 2024", "PP 12 Tahun 2023", "PMK 68 Tahun 2020",
                                                                                     "PER-7/PJ/2023", "PER-23/PJ/2025"}


def test_leak_guard_drops_document_own_watchlist_entry():
    it = EvalItem("uji", "PMK 168 Tahun 2023", "PERATURAN TANPA KATA KUNCI APA PUN", "dasar")
    assert score_set([it], load_watchlist(), prevent_leak=False).predictions[0].category == "tidak_relevan"
    it2 = EvalItem("uji", "PMK 168 Tahun 2023", "PERUBAHAN ATAS PERATURAN MENTERI KEUANGAN NOMOR 168 TAHUN 2023", "dasar")
    assert score_set([it2], load_watchlist()).predictions[0].category == "tidak_relevan"


def test_rules_v2_on_real_titles():
    wl = load_watchlist()
    kasus = [
        ("KEP-652/PJ/2019", "PENETAPAN PEMOTONG PPH PASAL 23 DAN/ATAU PASAL 26 YANG DIHARUSKAN MEMBUAT BUKTI PEMOTONGAN", "tidak_relevan"),
        ("PER-5/PJ/2024", "BENTUK DAN TATA CARA PEMBUATAN BUKTI PEMOTONGAN DAN/ATAU PEMUNGUTAN PAJAK, SERTA BENTUK, ISI, "
         "TATA CARA PENGISIAN, DAN PENYAMPAIAN SURAT PEMBERITAHUAN MASA BAGI INSTANSI PEMERINTAH", "prosedural"),
        ("UU 7 Tahun 2021", "HARMONISASI PERATURAN PERPAJAKAN", "perlu_ditinjau"),
        ("PP 29 Tahun 2020", "FASILITAS PAJAK PENGHASILAN DALAM RANGKA PENANGANAN CORONA VIRUS DISEASE 2019", "perlu_ditinjau"),
        ("PMK 114 Tahun 2025", "PERLAKUAN ATAS BANTUAN ATAU SUMBANGAN TERMASUK ZAKAT ATAU SUMBANGAN KEAGAMAAN YANG SIFATNYA "
         "WAJIB, SERTA HARTA HIBAHAN DALAM PAJAK PENGHASILAN", "dasar"),
        ("PMK 31 Tahun 2021", "PAJAK PENJUALAN ATAS BARANG MEWAH ATAS PENYERAHAN BARANG KENA PAJAK YANG TERGOLONG MEWAH "
         "BERUPA KENDARAAN BERMOTOR TERTENTU YANG DITANGGUNG PEMERINTAH", "tidak_relevan"),
    ]
    for ident, judul, harapan in kasus:
        [p] = score_set([EvalItem("uji", ident, judul, "x")], wl).predictions
        assert p.category == harapan, (ident, p.reasons)


def test_enrichment_statistics():
    rekaman = [
        {"tanggal_feed": "2026-09-01", "teks_ditetapkan": "2026-09-01", "teks_diundangkan": "2026-09-08", "selisih": [
            "tanggal pengundangan: teks 2026-09-08, metadata JDIH 2026-09-07",
            "berlaku surut: mulai berlaku sebelum tanggal pengundangan"], "retroaktif": True, "galat": []},
        {"tanggal_feed": "2026-09-12", "portal_penetapan": "2026-09-12", "diundangkan_metadata": "2026-09-20",
         "teks_mulai": "2026-09-20", "selisih": [], "galat": ["x"]},
        {"tanggal_feed": "2026-09-20", "portal_penetapan": "2026-09-19", "keputusan": True, "selisih": [
            "pencabutan PMK 1 Tahun 2020 ada di teks tetapi tidak tercatat di relasi JDIH"], "galat": []},
    ]
    s = enrichment_stats(rekaman)
    assert s["dokumen"] == 3 and s["teks_terbaca"] == 2 and s["dokumen_dengan_selisih"] == 2
    assert s["selisih_per_jenis"] == {"tanggal pengundangan": 1, "pencabutan": 1}
    assert s["berlaku_surut"] == 1 and s["galat"] == 1
    assert s["pengundangan_dari_metadata"] == 1 and s["keputusan_tanpa_pengundangan"] == 1
    assert s["tanggal_feed_sama_penetapan"] == 2
    assert s["tanggal_feed_minus_pengundangan_hari"] == {"n": 2, "min": -8, "median": -7.5, "p90": -7, "maks": -7}


def test_status_latency():
    c = ImpactNote("x", "PMK 1 Tahun 2027", "j", "", "", "2027-02-10T08:00:00", "dasar", diundangkan="2027-02-03")
    tanpa = ImpactNote("y", "PMK 2 Tahun 2027", "j", "", "", "2027-02-10T08:00:00", "dasar")
    assert status_latency([c, tanpa]) == [7]


def test_cli_monitor_evaluate(tmp_path, capsys):
    from taxagent.cli import main

    rekaman = tmp_path / "sampel.json"
    rekaman.write_text(json.dumps([{"tanggal_feed": "2026-09-10", "teks_diundangkan": "2026-09-08", "selisih": [], "galat": []}]))
    assert main(["monitor-evaluate", "--output", str(tmp_path), "--enrichment", str(rekaman)]) == 0
    keluaran = capsys.readouterr().out
    assert "pajakgoid  n= 1214 positif= 41 ditandai= 81" in keluaran and "recall=87.8%" in keluaran
    md = (tmp_path / "pantau_evaluasi.md").read_text(encoding="utf-8")
    assert "| pajakgoid | 1214 | 41 | 81 | 36 | 45 | 5 |" in md and "tanggal_feed_minus_pengundangan_hari" in md
    data = json.loads((tmp_path / "pantau_evaluasi.json").read_text(encoding="utf-8"))
    assert data["set"]["kurasi"]["biner"]["recall"] == pytest.approx(1.0)


def test_prospective_filter_keeps_items_dated_on_or_after_the_freeze(tmp_path, capsys):
    from taxagent.cli import main
    from taxagent.monitor.evaluation import issued_since

    items = [EvalItem("s", "a", "A", "dasar", date="2026-11-20"), EvalItem("s", "b", "B", "dasar", date="20-11-2026"),
             EvalItem("s", "c", "C", "dasar")]
    assert [it.id for it in issued_since(items, "2026-11-16")] == ["a", "b"]
    assert issued_since([EvalItem("s", "d", "D", "dasar", date="01-11-2026")], "2026-11-16") == []
    assert main(["monitor-evaluate", "--output", str(tmp_path), "--since", "2026-10-01"]) == 0
    out = capsys.readouterr().out
    assert "Uji prospektif" in out and "pajakgoid  n=    0" in out and "kurasi     n=    0" in out
    data = json.loads((tmp_path / "pantau_evaluasi_sejak_2026-10-01.json").read_text(encoding="utf-8"))
    assert data["sejak"] == "2026-10-01"
