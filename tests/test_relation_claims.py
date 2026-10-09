from __future__ import annotations

from taxagent.corpus.relation_claims import collect


def _rel(nama, arah, jenis, nomor, slug):
    return {"nama": nama, "arah": arah, "jenis_efek": jenis, "nomor": nomor, "slug": slug,
            "tgl_mulai_berlaku": "2024-01-01"}


HAL = [
    ("a", {"url": "https://jdih.kemenkeu.go.id/dok/pmk-168-tahun-2023", "nomor": "PMK 168 TAHUN 2023", "relasi": [
        _rel("Mencabut", "keluar", "mencabut", "252/PMK.03/2008", "252-pmk-03-2008"),
        _rel("Mencabut", "keluar", "mencabut", "Nomor 9 Tahun 1999", "pmk-9-tahun-1999"),
    ]}),
    ("b", {"url": "https://jdih.kemenkeu.go.id/dok/252-pmk-03-2008", "nomor": "252/PMK.03/2008", "relasi": [
        _rel("Dicabut dengan", "masuk", "mencabut", "PMK 168 TAHUN 2023", "pmk-168-tahun-2023"),
        _rel("Mengubah", "keluar", "mengubah", "252/PMK.03/2008", "252-pmk-03-2008"),
    ]}),
    ("c", {"url": "https://jdih.kemenkeu.go.id/dok/perpu-3-tahun-2008", "nomor": "PERPU 3 TAHUN 2008", "relasi": [
        _rel("Ditetapkan Menjadi Undang-Undang", "keluar", "lain", "UU 7 TAHUN 2009", "uu-7-tahun-2009"),
    ]}),
    ("d", {"url": "https://jdih.kemenkeu.go.id/dok/uu-7-tahun-2009", "nomor": "UU 7 TAHUN 2009", "relasi": [
        _rel("Menetapkan Menjadi Undang-Undang", "keluar", "lain", "PERPU 3 TAHUN 2008", "perpu-3-tahun-2008"),
        _rel("Mengubah", "keluar", "mengubah", "PP 57TAHUN2005", "slug-yang-tidak-ada"),
    ]}),
]
KUNCI = {"a": "PMK 168 Tahun 2023", "b": "PMK 252 Tahun 2008", "c": "PERPPU 3 Tahun 2008", "d": "UU 7 Tahun 2009"}


def _klaim():
    klaim, lap = collect(HAL, KUNCI)
    return {(k.dari, k.jenis, k.ke): k for k in klaim}, lap


def test_two_sides_joined_via_slug():
    k, _ = _klaim()
    x = k[("PMK 168 Tahun 2023", "mencabut", "PMK 252 Tahun 2008")]
    assert sorted(x.dicatat_di) == ["halaman_pengubah", "halaman_target"]
    assert not x.one_sided and not x.ke_stub and (x.dari_id, x.ke_id) == ("a", "b")


def test_target_outside_corpus_becomes_one_sided_stub():
    k, lap = _klaim()
    x = k[("PMK 168 Tahun 2023", "mencabut", "PMK 9 Tahun 1999")]
    assert x.ke_stub and x.one_sided
    assert lap["target_stub"] == 2


def test_broken_number_normalised_when_slug_missing():
    k, _ = _klaim()
    assert ("UU 7 Tahun 2009", "mengubah", "PP 57 Tahun 2005") in k


def test_other_relation_direction_from_name_and_self_dropped():
    k, lap = _klaim()
    x = k[("PERPPU 3 Tahun 2008", "ditetapkan_menjadi", "UU 7 Tahun 2009")]
    assert sorted(x.dicatat_di) == ["halaman_pengubah", "halaman_target"]
    assert len(lap["diri_sendiri"]) == 1
    assert lap["klaim_unik"] == len(k) == 4
