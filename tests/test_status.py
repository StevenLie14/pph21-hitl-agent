from __future__ import annotations

import datetime as dt

from taxagent.corpus.status import Edge, check_integrity, compute, interval

D = dt.date.fromisoformat
CABUT_252 = Edge("PMK 168 Tahun 2023", "mencabut", "PMK 252 Tahun 2008", "eksplisit", "2024-01-01")


def test_revoked_from_effective_date_not_before():
    assert compute("PMK 252 Tahun 2008", D("2023-12-31"), [CABUT_252], []).status == "berlaku"
    s = compute("PMK 252 Tahun 2008", D("2024-01-01"), [CABUT_252], [])
    assert (s.status, s.since, s.by) == ("dicabut", "2024-01-01", ["PMK 168 Tahun 2023"])


def test_not_yet_effective_expired_and_enacted_as():
    assert compute("PMK 168 Tahun 2023", D("2023-12-15"), [], [], start="2024-01-01").status == "belum_berlaku"
    assert compute("PMK 10 Tahun 2025", D("2026-01-05"), [], [], valid_until="2025-12-31").status == "berakhir"
    perppu = Edge("PERPPU 2 Tahun 2022", "ditetapkan_menjadi", "UU 6 Tahun 2023", "eksplisit", "2023-03-31")
    assert compute("PERPPU 2 Tahun 2022", D("2024-01-01"), [], [perppu]).status == "ditetapkan_menjadi"


def test_partial_and_amended():
    e = Edge("PP 58 Tahun 2023", "mencabut_sebagian", "PP 80 Tahun 2010", "eksplisit", "2024-01-01",
             affected_articles=["2"])
    s = compute("PP 80 Tahun 2010", D("2024-06-01"), [e], [])
    assert (s.status, s.lapsed_articles) == ("berlaku_sebagian", ["2"])
    u = Edge("PMK 72 Tahun 2025", "mengubah", "PMK 10 Tahun 2025", "eksplisit", "2025-10-28")
    assert compute("PMK 10 Tahun 2025", D("2025-11-01"), [u], []).status == "berlaku_diubah"


def test_revoked_paragraph_does_not_void_article():
    e = Edge("PP 58 Tahun 2023", "mencabut_sebagian", "PP 80 Tahun 2010", "eksplisit", "2024-01-01",
             affected_articles=["2(3)", "7"])
    s = compute("PP 80 Tahun 2010", D("2024-06-01"), [e], [])
    assert (s.status, s.lapsed_articles, s.lapsed_paragraphs) == ("berlaku_sebagian", ["7"], {"2": ["3"]})


def test_implied_full_revocation_only_when_not_amending_others():
    t = Edge("PER-10/PJ/2024", "mencabut", "PER-9/PJ/2020", "tersirat", "2024-05-01", via="PER-5/PJ/2017")
    hanya = [Edge("PER-9/PJ/2020", "mengubah", "PER-5/PJ/2017", "eksplisit")]
    banyak = hanya + [Edge("PER-9/PJ/2020", "mengubah", "PER-1/PJ/2019", "eksplisit")]
    assert compute("PER-9/PJ/2020", D("2025-01-01"), [t], hanya).status == "dicabut"
    assert compute("PER-9/PJ/2020", D("2025-01-01"), [t], banyak).status == "berlaku_sebagian"


def test_no_evidence_unknown_and_pajak_label():
    r = Edge("X", "mencabut", "Y", "tanpa_bukti", "2010-01-01")
    assert compute("Y", D("2020-01-01"), [r], []).status == "tidak_diketahui"
    s = compute("KEP-1/PJ/1999", D("2020-01-01"), [], [], pajak_label="Dicabut")
    assert s.status == "dicabut" and not s.certain


def test_estimated_date_uncertain_and_never_revived():
    e = Edge("B", "mencabut", "A", "eksplisit", None, estimated_date="2015-01-01")
    s = compute("A", D("2016-01-01"), [e], [])
    assert s.status == "dicabut" and not s.certain
    assert compute("A", D("2020-01-01"), [e], []).status == "dicabut"


def test_interval_and_integrity():
    assert interval("PMK 252 Tahun 2008", [CABUT_252], [], start="2008-12-31") == {
        "berlaku_mulai": "2008-12-31", "berhenti_pada": "2024-01-01"}
    e = [CABUT_252, Edge("PMK 252 Tahun 2008", "mencabut", "PMK 168 Tahun 2023", "eksplisit", "2009-01-01"),
         Edge("PMK 9 Tahun 2024", "mencabut", "PMK 252 Tahun 2008", "eksplisit", "2024-02-01")]
    jenis = {t["jenis"] for t in check_integrity(e, {"PMK 168 Tahun 2023": 2023, "PMK 252 Tahun 2008": 2008,
                                                     "PMK 9 Tahun 2024": 2024}, {})}
    assert {"siklus_pencabutan", "target_lebih_baru", "dicabut_penuh_berkali"} <= jenis
