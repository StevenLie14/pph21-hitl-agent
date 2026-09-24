from __future__ import annotations

import datetime as dt

import pytest

from taxagent.agent import stale_reports as P
from taxagent.taxes.pph21.calc.rates import available_years

BARU = max(available_years()) + 1
HARI = dt.date(BARU, 2, 10)
SEBELUM = dt.date(BARU - 1, 10, 18)


def _graf(status=None):
    def cari(regulation, date):
        if status is None:
            return {"berhasil": False, "galat": f"'{regulation}' tidak ada di graf."}
        if status == "mati":
            return {"berhasil": False, "galat": "graf tidak bisa diakses: ConnectionError"}
        return {"berhasil": True, "peraturan": [{"peraturan": "PMK-252-2008", "status": status, "oleh": ["PMK-168-2023"],
                                                 "sejak": "2024-01-01"}]}
    return cari


def test_rate_table_missing(tmp_path):
    f = tmp_path / "m.jsonl"
    h = P.report("tabel_tarif_belum_ada", "tool menolak tahun", tanggal_fakta=f"{BARU}-01-31", f=f, hari_ini=HARI)
    assert h["berhasil"] and h["dicatat"] and h["nomor"] == 1
    ada = P.report("tabel_tarif_belum_ada", "x", tanggal_fakta=f"{max(available_years())}-05-01", f=f)
    assert not ada["berhasil"] and "sudah ada" in ada["galat"]
    kosong = P.report("tabel_tarif_belum_ada", "x", f=f)
    assert not kosong["berhasil"] and "tanggal_fakta" in kosong["galat"]
    lama = P.report("tabel_tarif_belum_ada", "x", tanggal_fakta="2010-05-01", f=f)
    assert not lama["berhasil"] and "di luar cakupan" in lama["galat"]


def test_future_tax_year_is_not_stale(tmp_path):
    f = tmp_path / "m.jsonl"
    h = P.report("tabel_tarif_belum_ada", "x", tanggal_fakta=f"{BARU}-01-31", f=f, hari_ini=SEBELUM)
    assert not h["berhasil"] and "belum berjalan" in h["galat"] and not f.exists()


def test_dedupe_and_mark(tmp_path):
    f = tmp_path / "m.jsonl"
    a = P.report("tabel_tarif_belum_ada", "x", tanggal_fakta=f"{BARU}-01-31", f=f, hari_ini=HARI)
    b = P.report("tabel_tarif_belum_ada", "y", tanggal_fakta=f"{BARU}-03-31", f=f, hari_ini=HARI)
    assert b["berhasil"] and not b["dicatat"] and b["nomor"] == a["nomor"]
    c = P.report("tabel_tarif_belum_ada", "z", tanggal_fakta=f"{BARU}-03-31", f=f,
                 hari_ini=HARI + dt.timedelta(days=P.REPEAT_DAYS + 1))
    assert c["dicatat"] and c["nomor"] == 2
    assert len(P.monitor_warnings(f)) == 2
    P.resolve(1, "ditindaklanjuti", f=f)
    assert [r["nomor"] for r in P.open_reports(f)] == [2]
    with pytest.raises(ValueError):
        P.resolve(1, "tidak_perlu", f=f)


def test_unknown_regulation(tmp_path):
    f = tmp_path / "m.jsonl"
    assert not P.report("peraturan_tidak_dikenal", "x", f=f)["berhasil"]
    h = P.report("peraturan_tidak_dikenal", "pengguna menyebut", "PMK 15 Tahun 2026", graf=_graf(None), f=f)
    assert h["dicatat"] and P.open_reports(f)[0]["objek"] == "PMK 15 Tahun 2026"
    ada = P.report("peraturan_tidak_dikenal", "x", "PMK 252 Tahun 2008", graf=_graf("dicabut"), f=f)
    assert not ada["berhasil"] and "ada di graf" in ada["galat"]
    mati = P.report("peraturan_tidak_dikenal", "x", "PMK 99 Tahun 2026", graf=_graf("mati"), f=f)
    assert mati["dicatat"] and "tidak bisa dicek" in P.open_reports(f)[-1]["bukti"]["graf"]


@pytest.mark.parametrize("status,dicatat", [("dicabut", True), ("berakhir", True), ("berlaku", False),
                                            ("berlaku_diubah", False), ("tidak_diketahui", False)])
def test_legal_basis_not_in_force(tmp_path, status, dicatat):
    h = P.report("dasar_hukum_tidak_berlaku", "x", "PMK 252 Tahun 2008", graf=_graf(status), f=tmp_path / "m.jsonl")
    assert h["berhasil"] is dicatat


def test_wrong_arguments(tmp_path):
    assert "tidak dikenal" in P.report("tebakan", "x", f=tmp_path / "m")["galat"]
    assert "keterangan kosong" in P.report("tabel_tarif_belum_ada", " ", f=tmp_path / "m")["galat"]


def test_via_registry(tmp_path, monkeypatch):
    from taxagent.tools import call_tool

    monkeypatch.setenv("PPH21_PERMINTAAN_AGENT", str(tmp_path / "m.jsonl"))
    monkeypatch.setenv("PPH21_TOOL_GRAF", "0")
    h = call_tool("report_possibly_stale", reason="peraturan_tidak_dikenal", details="pengguna menyebutnya",
                  regulation="PMK 99 Tahun 2026")
    assert h["dicatat"] and (tmp_path / "m.jsonl").exists()


def test_new_year_suggestion_mentions_tool(monkeypatch):
    from taxagent.taxes.pph21 import tools as T
    from taxagent.tools import call_tool

    monkeypatch.setattr(T, "_today", lambda: HARI)
    h = call_tool("calculate_pph21_permanent_monthly", gaji_pokok=9000000, status_ptkp="TK/0",
                  kutipan_status_ptkp="TK/0", masa_pajak=1, tahun_pajak=BARU)
    assert not h["berhasil"] and "report_possibly_stale" in h["saran"]


def test_future_tax_year_suggestion_says_estimate(monkeypatch):
    from taxagent.taxes.pph21 import tools as T
    from taxagent.tools import call_tool

    monkeypatch.setattr(T, "_today", lambda: SEBELUM)
    h = call_tool("calculate_pph21_permanent_monthly", gaji_pokok=9000000, status_ptkp="TK/0",
                  kutipan_status_ptkp="TK/0", masa_pajak=1, tahun_pajak=BARU)
    assert not h["berhasil"] and "belum berjalan" in h["saran"] and "PERKIRAAN" in h["saran"]
    assert "JANGAN panggil report_possibly_stale" in h["saran"]
