from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from taxagent.monitor import (
    CODE_FAILED,
    CODE_FINDINGS,
    CODE_NONE,
    MonitorState,
    RegulationId,
    SourceError,
    canon_id,
    classify,
    find_all,
    from_slug,
    load,
    load_watchlist,
    parse_feed,
    run,
    save,
)
from taxagent.monitor.identity import canon_id_query, find_all_query
from taxagent.taxes.pph21.calc.rates import DATA_DIR

FIXTURE = Path(__file__).parent / "fixtures" / "pantau"
FEED = (FIXTURE / "jdih_feed_2026-10-04.json").read_bytes()
_KURASI = yaml.safe_load((DATA_DIR / "pantau_evaluasi.yaml").read_text(encoding="utf-8"))["kurasi"]
BERLABEL = {
    "positif": [dict(k, kategori=k.get("harapan", k["label"])) for k in _KURASI if k["label"] != "tidak_relevan"],
    "negatif": [k for k in _KURASI if k["label"] == "tidak_relevan"],
}


@pytest.mark.parametrize(
    "teks,harapan",
    [
        ("PMK 168 TAHUN 2023", "PMK 168 Tahun 2023"),
        ("Peraturan Menteri Keuangan Nomor 168 Tahun 2023", "PMK 168 Tahun 2023"),
        ("101/PMK.010/2016", "PMK 101 Tahun 2016"),
        ("PER-6/PJ/2026", "PER-6/PJ/2026"),
        ("PER - 11 / PJ / 2025", "PER-11/PJ/2025"),
        ("KEP-77/PP/2025", "KEP-77/PP/2025"),
        ("KMK 46/MK/EF.2/2026", "KMK 46/EF2/2026"),
        ("66/MK/BC/2026", "KMK 66/BC/2026"),
        ("KMK 185 TAHUN 2026", "KMK 185 Tahun 2026"),
        ("Peraturan Pemerintah Pengganti Undang-Undang Nomor 1 Tahun 2020", "PERPPU 1 Tahun 2020"),
        ("PERPU 1 TAHUN 2020", "PERPPU 1 Tahun 2020"),
        ("Undang-Undang Nomor 7 Tahun 2021", "UU 7 Tahun 2021"),
        ("PP Nomor 58 Tahun 2023", "PP 58 Tahun 2023"),
    ],
)
def test_canon_id(teks, harapan):
    assert str(canon_id(teks)) == harapan


@pytest.mark.parametrize(
    "slug,teks",
    [
        ("pmk-168-tahun-2023", "PMK 168 Tahun 2023"),
        ("101-pmk-010-2016", "101/PMK.010/2016"),
        ("250-pmk-03-2008", "250/PMK.03/2008"),
        ("per-6pj2026", "PER-6/PJ/2026"),
        ("kep-77pp2025", "KEP-77/PP/2025"),
        ("kmk-46mkef22026", "KMK 46/MK/EF.2/2026"),
        ("66mkbc2026", "66/MK/BC/2026"),
        ("pp-58-tahun-2023", "PP 58 Tahun 2023"),
        ("uu-4-tahun-2026", "UU 4 Tahun 2026"),
    ],
)
def test_slug_and_text_give_same_identity(slug, teks):
    assert from_slug(slug) == canon_id(teks)


def test_identities_that_must_differ():
    assert canon_id("PER-6/PJ/2026") != canon_id("PER-6/BC/2026")
    assert canon_id("KMK 46/MK/EF.2/2026") != canon_id("KMK 46 Tahun 2026")
    assert canon_id("101/PMK.010/2016") == canon_id("PMK Nomor 101 Tahun 2016")


@pytest.mark.parametrize(
    ("teks", "harapan"),
    [
        ("PMK 168/2023 Pasal 9 PTKP karyawati", "PMK 168 Tahun 2023"),
        ("pp 58/2023 pasal 4", "PP 58 Tahun 2023"),
        ("UU 36/2008", "UU 36 Tahun 2008"),
        ("PMK No. 66/2023", "PMK 66 Tahun 2023"),
        ("PER 16/PJ/2016 Pasal 20", "PER-16/PJ/2016"),
        ("UU HPP Pasal 17 lapisan tarif", "UU 7 Tahun 2021"),
        ("PMK 16/PMK.03/2010 Pasal 6", "PMK 16 Tahun 2010"),
        ("PP 58 Tahun 2023 Pasal 2", "PP 58 Tahun 2023"),
    ],
)
def test_canon_id_query_typed_forms(teks, harapan):
    assert str(canon_id_query(teks)) == harapan


def test_find_all_query_every_typed_form():
    t = "Teman bilang UU 36/2008 dan PMK-101/PMK.010/2016 berlaku, juga UU HPP; gaji 20.000.000/2025, KMK 564/2004."
    assert [str(i) for i in find_all_query(t)] == ["UU 36 Tahun 2008", "PMK 101 Tahun 2016"]
    assert [str(i) for i in find_all_query("UU 7/2021 (UU HPP) dan PP 58/2023")] == ["UU 7 Tahun 2021", "PP 58 Tahun 2023"]


@pytest.mark.parametrize("teks", ["pp 58-2023", "PP 58 thn 2023", "PP 58 th. 2023", "PP No. 58 Thn. 2023"])
def test_find_all_query_loose_year_separators(teks):
    assert [str(i) for i in find_all_query(teks.upper())] == ["PP 58 Tahun 2023"]


@pytest.mark.parametrize("teks", ["UU HPP", "Harmonisasi Peraturan Perpajakan", "PP 58 2023", "PP58", "gaji 10-2025"])
def test_find_all_query_reads_numbered_forms_only(teks):
    assert find_all_query(teks.upper()) == []


@pytest.mark.parametrize("teks", ["UU PPh Pasal 21", "KMK 564/2004", "gaji 10/2025", "pasal 21 ayat 3"])
def test_canon_id_query_does_not_guess(teks):
    assert canon_id_query(teks) is None


def test_canon_id_corpus_text_unchanged():
    assert canon_id("PMK 168/2023") is None


@pytest.mark.parametrize(
    "teks",
    ["KMK 46/MK/EF.2/2026", "66/MK/BC/2026", "11/KM.7/2024", "PER-6/PJ/2026", "KEP-59/PP/2026",
     "PMK 168 Tahun 2023", "101/PMK.010/2016", "PERPU 1 TAHUN 2020"],
)
def test_identity_str_roundtrips(teks):
    ident = canon_id(teks)
    assert canon_id(str(ident)) == ident


def test_article_slug_not_regulation():
    assert from_slug("df8d204b-cd6a-48d4-b6ab-cb3db785fda4") is None


def test_subnumbered_number_not_its_base_number():
    assert str(canon_id("Peraturan Menteri Keuangan Nomor 143.1/PMK.01/2009 tentang ...")) == "PMK 143.1 Tahun 2009"
    assert str(canon_id("berdasarkan 206.2/PMK.01/2014")) == "PMK 206.2 Tahun 2014"
    assert str(canon_id("Keputusan Menteri Keuangan Nomor 12.1/KMK.04/1998")) == "KMK 12.1/KMK04/1998"
    assert [str(i) for i in find_all("PMK 206.1/PMK.01/2014 dan 206.2/PMK.01/2014 dan 1/PMK.01/2014")] == \
        ["PMK 206.1 Tahun 2014", "PMK 206.2 Tahun 2014", "PMK 1 Tahun 2014"]
    assert canon_id("143.1/PMK.01/2009") != canon_id("1/PMK.01/2009")
    assert str(canon_id("NO.143/PMK.03/2008")) == "PMK 143 Tahun 2008"
    assert str(from_slug("206-2-pmk-01-2014")) == "PMK 206.2 Tahun 2014"


@pytest.mark.parametrize("ident", [
    RegulationId("PMK", 143, 2009, sub=1), RegulationId("KMK", 12, 1998, "KMK04", sub=1),
    RegulationId("KEP", 7, 2011, "PP", sub=1), RegulationId("PMK", 168, 2023),
])
def test_subnumbered_identity_str_roundtrips(ident):
    assert canon_id(str(ident)) == ident


def test_search_all_in_amendment_title():
    teks = (
        "Perubahan atas Peraturan Menteri Keuangan Nomor 195/PMK.08/2020 tentang Lelang "
        "dan Peraturan Pemerintah Nomor 58 Tahun 2023"
    )
    assert find_all(teks) == [RegulationId("PMK", 195, 2020), RegulationId("PP", 58, 2023)]


def test_watchlist_valid():
    wl = load_watchlist()
    assert all(e.role in ("dasar", "fasilitas", "prosedural") for e in wl.regulations)
    assert all(not e.governs for e in wl.regulations if e.role == "fasilitas")
    ids = [e.identity for e in wl.regulations]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("kasus", BERLABEL["positif"], ids=[k["id"] for k in BERLABEL["positif"]])
def test_classify_positive(kasus):
    k = classify(kasus["judul"], doc_id=canon_id(kasus["id"]))
    assert k.category == kasus["kategori"], k.reasons
    assert set(kasus.get("key", [])) <= set(k.affected_keys), k.affected_keys
    assert set(kasus.get("pemicu", [])) <= set(k.triggers)
    if k.category == "fasilitas":
        assert not k.affected_keys


@pytest.mark.parametrize("kasus", BERLABEL["negatif"], ids=[k["id"] for k in BERLABEL["negatif"]])
def test_classify_negative(kasus):
    k = classify(kasus["judul"], doc_id=canon_id(kasus["id"]))
    assert k.category == "tidak_relevan", k.reasons


def test_real_feed_gives_no_false_alarm():
    dokumen = parse_feed(FEED)
    wl = load_watchlist()
    alarm = [d.title for d in dokumen if not d.artikel and classify(d.title, d.subject, d.identity, wl).needs_review]
    assert alarm == []


def test_parse_real_feed():
    dokumen = parse_feed(FEED)
    assert len(dokumen) == 100
    assert sum(d.artikel for d in dokumen) == 2
    assert all(d.identity is not None for d in dokumen if not d.artikel)
    pertama = dokumen[0]
    assert pertama.slug == "kmk-46mkef22026" and str(pertama.identity) == "KMK 46/EF2/2026"


@pytest.mark.parametrize(
    "mentah",
    [b"<html>maintenance</html>", b'{"version": "x", "items": []}', b'{"version": "https://jsonfeed.org/version/1", "items": []}'],
)
def test_broken_or_empty_feed_is_failure(mentah):
    with pytest.raises(SourceError):
        parse_feed(mentah)


def _feed_dengan(item_tambahan: dict) -> list:
    data = json.loads(FEED)
    data["items"].insert(0, item_tambahan)
    return parse_feed(json.dumps(data))


ITEM_PMK_PTKP = {
    "id": "https://jdih.kemenkeu.go.id/dok/pmk-90-tahun-2027",
    "url": "https://jdih.kemenkeu.go.id/dok/pmk-90-tahun-2027",
    "title": "PMK 90 TAHUN 2027 ",
    "content_html": "Penyesuaian Besarnya Penghasilan Tidak Kena Pajak ",
    "date_modified": "2027-06-20T12:00:00.000Z",
}


def test_first_round_then_new_documents(tmp_path):
    berkas = tmp_path / "status.json"
    status = MonitorState()

    h1 = run(parse_feed(FEED), status, now="2026-10-04T08:00:00")
    assert h1.first_run and h1.exit_code == CODE_NONE
    assert len(h1.new_documents) == 98 and h1.dropped_articles == 2
    save(status, berkas)

    status = load(berkas)
    h2 = run(parse_feed(FEED), status, now="2026-10-05T08:00:00")
    assert h2.exit_code == CODE_NONE and not h2.new_documents and not h2.first_run

    h3 = run(_feed_dengan(ITEM_PMK_PTKP), status, now="2027-06-21T08:00:00")
    assert h3.exit_code == CODE_FINDINGS
    [c] = h3.new_notes
    assert c.kategori == "dasar" and "ptkp" in c.key_terdampak and "PP 58 Tahun 2023" in c.pemicu
    assert c.first_seen == "2027-06-21T08:00:00" and c.tanggal_feed == "2027-06-20"
    assert c.status_review == "baru" and c.diterapkan_ke_yaml is False
    save(status, berkas)

    status = load(berkas)
    assert [x.identitas for x in status.catatan] == ["PMK 90 Tahun 2027"]
    assert status.dilihat[ITEM_PMK_PTKP["id"]]["first_seen"] == "2027-06-21T08:00:00"


def test_unknown_status_version_rejected(tmp_path):
    berkas = tmp_path / "status.json"
    berkas.write_text('{"versi": 99}', encoding="utf-8")
    with pytest.raises(ValueError):
        load(berkas)


def test_cli_offline_and_exit_code(tmp_path, capsys):
    from taxagent.cli import main

    feed = tmp_path / "feed.json"
    feed.write_bytes(FEED)
    status = tmp_path / "status.json"
    assert main(["monitor", "--feed-file", str(feed), "--status", str(status), "--no-stale-check"]) == CODE_NONE
    assert status.exists()

    data = json.loads(FEED)
    data["items"].insert(0, ITEM_PMK_PTKP)
    feed.write_text(json.dumps(data), encoding="utf-8")
    assert main(["monitor", "--feed-file", str(feed), "--status", str(status), "--no-stale-check"]) == CODE_FINDINGS
    keluaran = capsys.readouterr().out
    assert "[DASAR] PMK 90 Tahun 2027" in keluaran and "ptkp" in keluaran


def test_cli_broken_source_is_failure_code_and_status_unchanged(tmp_path, capsys):
    from taxagent.cli import main

    feed = tmp_path / "feed.json"
    feed.write_text("<html>502 Bad Gateway</html>", encoding="utf-8")
    status = tmp_path / "status.json"
    assert main(["monitor", "--feed-file", str(feed), "--status", str(status), "--no-stale-check"]) == CODE_FAILED
    assert not status.exists()
    assert "PEMANTAU GAGAL" in capsys.readouterr().out
