from __future__ import annotations

import shutil

import pytest
import yaml
from test_monitor_text import AmbilPalsu, _feed, halaman

from taxagent.monitor import ImpactNote, MonitorState, load, save
from taxagent.monitor.classify import load_watchlist
from taxagent.monitor.jdih import parse_page
from taxagent.monitor.resilience import (
    PROVENANCE_FILE,
    check_canaries,
    check_stale,
    load_provenance,
    mark_checked,
    relation_fingerprint,
)
from taxagent.monitor.review import list_notes, mark
from taxagent.monitor.run import CODE_FAILED, CODE_WARNING, run, text_report
from taxagent.taxes.pph21.calc.rates import DATA_DIR

TAHUN_LENGKAP = [2024, 2025, 2026]


def _halaman_kanari(**ganti: str) -> dict:
    slug = {"PMK 168 Tahun 2023": "pmk-168-tahun-2023", "PP 58 Tahun 2023": "pp-58-tahun-2023", "PP 80 Tahun 2010": "pp-80-tahun-2010"}
    return {k: parse_page(ganti.get(s, halaman(s)), s) for k, s in slug.items()}


def _catatan(identitas="PMK 90 Tahun 2027", first_seen="2026-10-01T08:00:00", **kw) -> ImpactNote:
    return ImpactNote(
        id_dokumen=f"https://jdih.kemenkeu.go.id/dok/{identitas}", identitas=identitas, judul=identitas,
        perihal="", tanggal_feed="", first_seen=first_seen, kategori="dasar", **kw,
    )


def _status_segar(waktu="2026-10-04T08:00:00") -> MonitorState:
    return MonitorState(dilihat={"x": {"first_seen": waktu}}, run_terakhir=waktu, dokumen_baru_terakhir=waktu)


def test_provenance_covers_all_watchlist_keys_and_points_to_existing_rate_keys():
    prov = load_provenance()
    diatur = {k for e in load_watchlist().regulations for k in e.governs}
    assert diatur <= set(prov), diatur - set(prov)
    tarif = yaml.safe_load((DATA_DIR / "tarif_2024.yaml").read_text(encoding="utf-8"))
    for key, info in prov.items():
        assert info["dasar_hukum"] and info["terakhir_dicek"], key
        if info["lokasi"].startswith("tarif_*.yaml: "):
            assert info["lokasi"].split(": ", 1)[1] in tarif, key


def test_update_checked_only_forward_and_keeps_layout(tmp_path):
    berkas = tmp_path / "provenans.yaml"
    shutil.copy(PROVENANCE_FILE, berkas)
    asli = berkas.read_text(encoding="utf-8")

    assert mark_checked(["ptkp", "key_tak_dikenal"], "2027-01-15", berkas) == ["ptkp"]
    assert mark_checked(["ptkp"], "2026-01-01", berkas) == []
    prov = load_provenance(berkas)
    assert prov["ptkp"]["terakhir_dicek"] == "2027-01-15"
    assert prov["tarif_pasal_17"]["terakhir_dicek"] == load_provenance()["tarif_pasal_17"]["terakhir_dicek"]
    baru = berkas.read_text(encoding="utf-8")
    assert len(baru.splitlines()) == len(asli.splitlines())
    changed = [(a, b) for a, b in zip(asli.splitlines(), baru.splitlines()) if a != b]
    assert len(changed) == 1 and "2027-01-15" in changed[0][1]


def test_no_stale_warning_when_all_fresh():
    assert check_stale(_status_segar(), load_watchlist(), "2026-10-04T08:00:00", available_years=TAHUN_LENGKAP) == []


def test_current_year_rates_missing():
    [p] = check_stale(_status_segar(), load_watchlist(), "2026-10-04T08:00:00", available_years=[2024, 2025])
    assert "tarif_2026.yaml belum ada" in p and "tabel 2025" in p


def test_long_unchecked_key_becomes_warning():
    prov = {"ptkp": {"dasar_hukum": "PMK 101/2016", "terakhir_dicek": "2026-01-01"}, "natura": {"dasar_hukum": "PMK 66/2023"}}
    p = check_stale(_status_segar(), load_watchlist(), "2026-10-04T08:00:00", provenance=prov, available_years=TAHUN_LENGKAP)
    assert any("key ptkp terakhir dicek 2026-01-01" in x and "PMK 101/2016" in x for x in p)
    assert any("key natura belum pernah dicek" in x for x in p)


@pytest.mark.parametrize(
    "sekarang,harapan",
    [
        ("2026-10-04T08:00:00", None),
        ("2026-11-15T08:00:00", "berakhir dalam 46 hari"),
        ("2027-01-20T08:00:00", "sudah berakhir 20 hari lalu"),
        ("2027-04-01T08:00:00", None),
    ],
)
def test_last_dtp_facility_nearly_expired(sekarang, harapan):
    p = check_stale(_status_segar(sekarang), load_watchlist(), sekarang, provenance={}, available_years=[2024, 2025, 2026, 2027])
    fas = [x for x in p if "fasilitas terakhir" in x]
    if harapan is None:
        assert fas == []
    else:
        [x] = fas
        assert "PMK 105 Tahun 2025" in x and harapan in x and "2026-12-31" in x


def test_next_year_rates_requested_from_november():
    p = check_stale(_status_segar("2026-11-02T08:00:00"), load_watchlist(), "2026-11-02T08:00:00", provenance={}, available_years=TAHUN_LENGKAP)
    assert any("tarif_2027.yaml belum disiapkan" in x for x in p)


def test_quiet_feed_and_growing_queue():
    status = _status_segar("2026-09-01T08:00:00")
    status.catatan = [
        _catatan("PMK 90 Tahun 2026", first_seen="2026-09-01T08:00:00"),
        _catatan("PMK 91 Tahun 2026", status_review="relevan"),
        _catatan("PMK 92 Tahun 2026", status_review="diterapkan", diterapkan_ke_yaml=True),
    ]
    p = check_stale(status, load_watchlist(), "2026-10-04T08:00:00", provenance={}, available_years=TAHUN_LENGKAP)
    assert any("tidak memuat dokumen baru selama 33 hari" in x for x in p)
    assert any("1 catatan efek belum direview lebih dari 14 hari" in x for x in p)
    assert any("relevan belum diterapkan ke data: PMK 91 Tahun 2026" in x for x in p)


def test_empty_status_not_treated_as_quiet_feed():
    assert check_stale(MonitorState(), load_watchlist(), "2026-10-04T08:00:00", provenance={}, available_years=TAHUN_LENGKAP) == []


def test_canary_passes_on_real_page():
    hal = _halaman_kanari()
    assert check_canaries(hal) == []
    assert {"KodeRelasi", "Nama", "Nomor", "Slug", "TglMulaiBerlaku"} <= set(relation_fingerprint(hal))


def test_canary_fails_when_parser_loses_some_words():
    rusak = halaman("pp-80-tahun-2010").replace("Dicabut sebagian dengan", "Dicabut dengan")
    gagal = check_canaries(_halaman_kanari(**{"pp-80-tahun-2010": rusak}))
    assert gagal == ["PP 80 Tahun 2010: relasi masuk mencabut_sebagian PP 58 Tahun 2023 terbaca 0, seharusnya >= 1"]


def test_canary_fails_when_page_unreadable():
    hal = _halaman_kanari()
    del hal["PP 58 Tahun 2023"]
    assert "halaman kanari PP 58 Tahun 2023 tidak terbaca" in check_canaries(hal)


def test_run_with_failed_canary_is_failure_code_but_report_intact():
    status = MonitorState()
    run(_feed(), status, now="2026-10-04T08:00:00")
    rusak = halaman("pmk-168-tahun-2023").replace('KodeRelasi\\":\\"C', 'KodeRelasiX\\":\\"C')
    h = run(_feed(), status, now="2026-10-11T08:00:00",
            fetch=AmbilPalsu({"pmk-168-tahun-2023": (rusak, "")}), watchlist_check=True)
    assert h.exit_code == CODE_FAILED and h.canary_checked
    assert "PMK 168 Tahun 2023: relasi keluar mencabut terbaca 0" in h.errors
    teks = text_report(h)
    assert teks.startswith("PEMANTAU GAGAL: kanari gagal") and "watchlist diperiksa" in teks


def test_run_canary_passes_fingerprint_saved_then_structure_change_warned():
    status = MonitorState()
    run(_feed(), status, now="2026-10-04T08:00:00")
    h1 = run(_feed(), status, now="2026-10-11T08:00:00", fetch=AmbilPalsu(), watchlist_check=True)
    assert h1.canary_checked and not h1.errors and "KodeRelasi" in status.kanari_sidik
    assert h1.exit_code == CODE_WARNING

    status.kanari_sidik = status.kanari_sidik + ["KunciLama"]
    h2 = run(_feed(), status, now="2026-10-18T08:00:00", fetch=AmbilPalsu(), watchlist_check=True)
    assert any("struktur JSON relasi JDIH berubah" in p and "KunciLama" in p for p in h2.warnings)
    assert "KunciLama" not in status.kanari_sidik


def test_canary_fingerprint_saved_too(tmp_path):
    status = MonitorState(kanari_sidik=["KodeRelasi", "Nama"])
    save(status, tmp_path / "s.json")
    assert load(tmp_path / "s.json").kanari_sidik == ["KodeRelasi", "Nama"]


def test_mark_and_queue(tmp_path):
    prov = tmp_path / "provenans.yaml"
    shutil.copy(PROVENANCE_FILE, prov)
    status = MonitorState(catatan=[
        _catatan("PMK 90 Tahun 2027", key_terdampak=["ptkp"]),
        _catatan("PER-9/PJ/2027"),
    ])
    assert [n for n, _ in list_notes(status)] == [1, 2]

    c, maju = mark(status, 1, "relevan", "2027-07-01", articles=["Pasal 1"], applies_to=["Tahun Pajak 2027"],
                   note="PTKP naik", provenance_file=prov)
    assert (c.status_review, c.diterapkan_ke_yaml, maju) == ("relevan", False, [])
    assert c.pasal_terdampak == ["Pasal 1"] and c.berlaku_untuk == ["Tahun Pajak 2027"] and c.catatan_review == "PTKP naik"
    assert load_provenance(prov)["ptkp"]["terakhir_dicek"] != "2027-07-01"

    c, maju = mark(status, 1, "diterapkan", "2027-07-02", provenance_file=prov)
    assert c.diterapkan_ke_yaml and maju == ["ptkp"]
    assert load_provenance(prov)["ptkp"]["terakhir_dicek"] == "2027-07-02"
    assert [n for n, _ in list_notes(status)] == [2] and len(list_notes(status, include_all=True)) == 2

    with pytest.raises(ValueError):
        mark(status, 3, "relevan", "2027-07-02", provenance_file=prov)
    with pytest.raises(ValueError):
        mark(status, 2, "baru", "2027-07-02", provenance_file=prov)


def test_cli_monitor_review(tmp_path, capsys):
    from taxagent.cli import main

    prov = tmp_path / "provenans.yaml"
    shutil.copy(PROVENANCE_FILE, prov)
    berkas = tmp_path / "status.json"
    save(MonitorState(catatan=[_catatan("PMK 90 Tahun 2027", key_terdampak=["natura"])]), berkas)

    assert main(["monitor-review", "--status", str(berkas)]) == 0
    assert "#1 [baru] [DASAR] PMK 90 Tahun 2027" in capsys.readouterr().out

    assert main(["monitor-review", "--status", str(berkas), "--mark", "1", "--verdict", "tidak_relevan",
                 "--note", "hanya mengubah format", "--provenance", str(prov)]) == 0
    keluaran = capsys.readouterr().out
    assert "[tidak_relevan]" in keluaran and "terakhir_dicek dimajukan untuk: natura" in keluaran
    assert load(berkas).catatan[0].catatan_review == "hanya mengubah format"

    assert main(["monitor-review", "--status", str(berkas)]) == 0
    assert "Antrean review kosong" in capsys.readouterr().out
    assert main(["monitor-review", "--status", str(berkas), "--mark", "1"]) == 1
