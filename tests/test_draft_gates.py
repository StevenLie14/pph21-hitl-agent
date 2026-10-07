from __future__ import annotations

from pathlib import Path

import pytest

from taxagent.cli import main
from taxagent.update import assemble_draft, extract_amounts
from taxagent.update.assemble import Draft
from taxagent.update.gates import Effective, GateContext, GateResult, effective_from_text, effective_year

PTKP = (
    "Pasal 1 Besarnya penghasilan tidak kena pajak disesuaikan menjadi sebagai berikut: a. Rp60.000.000,00 (enam "
    "puluh juta rupiah) untuk diri Wajib Pajak orang pribadi; b. Rp5.000.000,00 (lima juta rupiah) tambahan untuk "
    "Wajib Pajak yang kawin; c. Rp60.000.000,00 (enam puluh juta rupiah) tambahan untuk seorang isteri; d. "
    "Rp5.000.000,00 (lima juta rupiah) tambahan untuk setiap anggota keluarga sedarah dan keluarga semenda dalam "
    "garis keturunan lurus serta anak angkat, yang menjadi tanggungan sepenuhnya, paling banyak 3 (tiga) orang "
    "untuk setiap keluarga. "
)
JABATAN = (
    "Pasal 2 Besarnya biaya jabatan sebagaimana dimaksud ditetapkan sebesar 5% (lima persen) dari penghasilan "
    "bruto, paling banyak Rp7.200.000,00 (tujuh juta dua ratus ribu rupiah) setahun atau paling banyak "
    "Rp600.000,00 (enam ratus ribu rupiah) sebulan. "
)
BERLAKU = "Pasal 3 Ketentuan sebagaimana dimaksud dalam Pasal 1 dan Pasal 2 mulai berlaku pada Tahun Pajak 2027. "


def draf(teks: str, tahun: int = 2027, keys=None, status=None) -> Draft:
    h = extract_amounts(teks, "s")
    return assemble_draft(tahun, [h], context=GateContext(keys, {"s": effective_from_text(teks, "s")},
                                                          source_status={"s": []} if status is None else status))


def gerbang(d: Draft) -> dict[str, GateResult]:
    return {g.code: g for g in d.gates}


def test_clean_text_held_only_by_second_extractor():
    d = draf(PTKP + JABATAN + BERLAKU)
    assert {p.key for p in d.berubah} == {"ptkp", "biaya_jabatan"}
    g = gerbang(d)
    assert all(g[k].passed for k in ("G1", "G2", "G3", "G5", "G6", "G7", "G8"))
    assert g["G4"].passed is None
    assert d.decision == "tahan" and len(d.decision_reason) == 1 and d.decision_reason[0].startswith("G4")


def test_g1_logic_key_from_phase1_holds():
    d = draf(PTKP + BERLAKU, keys=["ptkp", "natura"])
    assert gerbang(d)["G1"].passed is False and "natura" in gerbang(d)["G1"].reasons[0]


def test_g1_phase1_key_with_unread_number_holds():
    d = draf(PTKP + BERLAKU, keys=["ptkp", "biaya_pensiun"])
    assert gerbang(d)["G1"].passed is False
    assert any("biaya_pensiun" in a for a in gerbang(d)["G1"].reasons)


def test_g3_replaced_digit_without_words_held_even_without_change():
    salah = (PTKP + BERLAKU).replace("Rp60.000.000,00 (enam", "Rp66.000.000,00 (enam", 1)
    d = draf(salah)
    assert not d.berubah and d.yaml_text is None
    assert d.decision == "tahan" and gerbang(d)["G3"].passed is False


def test_g3_changed_number_without_words_held():
    tanpa = JABATAN.replace(" (enam ratus ribu rupiah)", "").replace(" (tujuh juta dua ratus ribu rupiah)", "")
    d = draf(tanpa + BERLAKU)
    assert [p.key for p in d.berubah] == ["biaya_jabatan"]
    assert gerbang(d)["G3"].passed is False


def test_g5_times_ten_typo_held():
    x10 = PTKP.replace("Rp60.000.000,00 (enam puluh juta rupiah) untuk diri",
                       "Rp600.000.000,00 (enam ratus juta rupiah) untuk diri")
    d = draf(x10 + BERLAKU)
    alasan = " ".join(gerbang(d)["G5"].reasons)
    assert gerbang(d)["G5"].passed is False and "rentang" in alasan and "rasio" in alasan


def test_g5_annual_max_must_be_twelve_times_monthly():
    d = draf(JABATAN.replace("Rp7.200.000,00 (tujuh juta dua ratus ribu rupiah)",
                             "Rp7.000.000,00 (tujuh juta rupiah)") + BERLAKU)
    assert gerbang(d)["G5"].passed is False
    assert any("12 x" in a for a in gerbang(d)["G5"].reasons)


def test_g5_experiment_modes(monkeypatch):
    x10 = PTKP.replace("Rp60.000.000,00 (enam puluh juta rupiah) untuk diri",
                       "Rp600.000.000,00 (enam ratus juta rupiah) untuk diri")
    monkeypatch.setenv("TAXAGENT_G5_MODE", "off")
    assert gerbang(draf(x10 + BERLAKU))["G5"].passed is True
    monkeypatch.setenv("TAXAGENT_G5_MODE", "ratio")
    alasan = " ".join(gerbang(draf(x10 + BERLAKU))["G5"].reasons)
    assert gerbang(draf(x10 + BERLAKU))["G5"].passed is False and "rasio" in alasan and "rentang" not in alasan


@pytest.mark.parametrize("berlaku,potongan", [
    ("Pasal 3 Ketentuan ini mulai berlaku pada Masa Pajak Juli 2027. ", "tengah tahun"),
    ("", "tidak terbaca"),
    ("Pasal 3 Ketentuan ini mulai berlaku pada Tahun Pajak 2028. ", "bukan tahun pajak draf"),
])
def test_g6_effective_date(berlaku, potongan):
    d = draf(PTKP + berlaku)
    assert gerbang(d)["G6"].passed is False and potongan in " ".join(gerbang(d)["G6"].reasons)


def test_g6_transitional_provision_holds():
    d = draf(PTKP + BERLAKU + "BAB III KETENTUAN PERALIHAN Pasal 4 Pemotongan sebelum ... ")
    assert gerbang(d)["G6"].passed is False


def test_g6_existing_year_table_never_ready():
    d = draf(PTKP + BERLAKU.replace("2027", "2026"), tahun=2026)
    assert d.berubah and gerbang(d)["G6"].passed is False
    assert "sudah ada" in " ".join(gerbang(d)["G6"].reasons)


def test_effective_year():
    assert effective_year(Effective("s", applies_to=["TAHUN PAJAK 2016"], start="2016-06-27"))[0] == 2016
    assert effective_year(Effective("s", start="2024-01-01"))[0] == 2024
    assert effective_year(Effective("s", start="2024-03-01"))[0] is None
    assert effective_year(Effective("s", applies_to=["MASA PAJAK JANUARI 2025"]))[0] == 2025


def test_text_without_change_stays_unchanged():
    d = draf(PTKP.replace("Rp60.000.000,00 (enam puluh juta rupiah)", "Rp54.000.000,00 (lima puluh empat juta rupiah)")
             .replace("Rp5.000.000,00 (lima juta rupiah)", "Rp4.500.000,00 (empat juta lima ratus ribu rupiah)") + BERLAKU)
    assert d.decision == "tidak_ada_perubahan"


def test_cli_phase1_keys_and_report(tmp_path: Path, capsys):
    s = tmp_path / "pmk.txt"
    s.write_text(PTKP + BERLAKU, encoding="utf-8")
    assert main(["draft-rates", "--year", "2027", "--source", str(s), "--output", str(tmp_path / "o"),
                 "--keys", "ptkp,mekanisme_pemotongan"]) == 1
    out = capsys.readouterr().out
    assert "Gerbang: tahan" in out and "mekanisme_pemotongan" in out
    md = (tmp_path / "o" / "draf_tarif_2027.md").read_text(encoding="utf-8")
    assert "## Gerbang: **tahan**" in md and "| G1 lingkup dan struktur | **gagal** |" in md


def test_leftover_words_mark_ocr_damaged_numbers():
    from decimal import Decimal

    from taxagent.update.amounts import clean_text
    b = clean_text("dikenai tarif 5046 (lima puluh persen) dan Rps0.000.000,00 (lima puluh juta rupiah)")
    assert len(b.mismatches) == 2
    b = clean_text("tarif 5% (lima persen) dan Rp50.000.000,00 (lima puluh juta rupiah)")
    assert not b.mismatches and {Decimal(5), Decimal(50000000)} <= b.verified


def test_g2_every_changed_number_has_quote():
    d = draf(PTKP + JABATAN + BERLAKU)
    g2 = gerbang(d)["G2"]
    assert g2.passed is True and "punya kutipan" in g2.reasons[0]


def test_g2_number_without_quote_holds():
    from taxagent.update.assemble import Comparison
    from taxagent.update.gates import _g2

    p = Comparison("ptkp", "berubah", {"wajib_pajak_sendiri": 54000000}, {"wajib_pajak_sendiri": 60000000}, ["s"])
    h = extract_amounts("Pasal 1 teks tanpa angka yang relevan.", "s")
    assert _g2([h], None, [p]).passed is False


def test_g8_revoked_source_holds():
    d = draf(PTKP + BERLAKU, status={"s": [("MENCABUT", "PMK 999 Tahun 2026")]})
    g8 = gerbang(d)["G8"]
    assert g8.passed is False and "dicabut oleh PMK 999 Tahun 2026" in g8.reasons[0] and d.decision == "tahan"


def test_g8_without_graph_not_run_and_holds():
    d = draf(PTKP + BERLAKU, status={})
    assert gerbang(d)["G8"].passed is False
    h = extract_amounts(PTKP + BERLAKU, "s")
    d = assemble_draft(2027, [h], context=GateContext(None, {"s": effective_from_text(PTKP + BERLAKU, "s")}))
    assert gerbang(d)["G8"].passed is None and any(a.startswith("G8") for a in d.decision_reason)


def test_graph_status_bounded_by_year():
    from taxagent.monitor.memory_graph import from_texts
    from taxagent.tools import regulation_graph as G
    from taxagent.update.source_status import status_from_graph

    dok = {"PMK 101 Tahun 2016": {"teks": "x", "mulai": "2016-06-01"},
           "PMK 122 Tahun 2015": {"teks": "y", "mulai": "2015-07-01"},
           "PMK 7 Tahun 2014": {"teks": "z"}}
    rel = [{"dari": "PMK 101 Tahun 2016", "jenis": "mencabut", "ke": "PMK 122 Tahun 2015", "tgl_efektif": "2016-07-01"},
           {"dari": "PMK 101 Tahun 2016", "jenis": "mengubah", "ke": "PMK 7 Tahun 2014", "bukti": "tanpa_bukti"}]
    G.use_client(from_texts(dok, rel))
    try:
        assert status_from_graph("PMK 122 Tahun 2015") == [("MENCABUT", "PMK 101 Tahun 2016")]
        assert status_from_graph("122/PMK.010/2015", until_year=2015) == []
        assert status_from_graph("PMK 101 Tahun 2016") == []
        assert status_from_graph("PMK 7 Tahun 2014") == [("MENGUBAH", "PMK 101 Tahun 2016 (klaim JDIH tanpa bukti teks)")]
        assert status_from_graph("PMK 7 Tahun 1999") is None
    finally:
        G.use_client(None)


def test_leftover_words_do_not_pair_other_unit_numbers_in_table():
    from taxagent.update.amounts import clean_text
    b = clean_text("lapisan 5% Rp60.000.000,00 15% (enam puluh juta rupiah) Rp5.950.000 (tiga persen)")
    assert not [x for x in b.mismatches if "15%" in x or "RP5950000" in x]


def test_double_ocr_dot_before_cents_normalised():
    from decimal import Decimal

    from taxagent.update.amounts import clean_text
    b = clean_text("melebihi Rp4.500.000.,00 (empat juta lima ratus ribu rupiah) sebulan")
    assert not b.mismatches and Decimal(4500000) in b.verified
