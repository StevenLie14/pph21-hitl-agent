from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from taxagent.cli import main
from taxagent.taxes.pph21.calc.rates import DATA_DIR, RateTable, load_raw
from taxagent.update import IN_SCOPE, DraftRejected, assemble_draft, extract_amounts, write_draft
from taxagent.update.amounts import clean_text, parse_rupiah, parse_terbilang
from taxagent.update.assemble import base_year_for

F = Path(__file__).parent / "fixtures" / "draf"
DASAR = sorted(F.glob("*.txt"))

PMK_2027 = (
    "Pasal 1 Besarnya penghasilan tidak kena pajak disesuaikan menjadi sebagai berikut: a. Rp60.000.000,00 (enam "
    "puluh juta rupiah) untuk diri Wajib Pajak orang pribadi; b. Rp5.000.000,00 (lima juta rupiah) tambahan untuk "
    "Wajib Pajak yang kawin; c. Rp60.000.000,00 (enam puluh juta rupiah) tambahan untuk seorang isteri yang "
    "penghasilannya digabung dengan penghasilan suami; d. Rp5.000.000,00 (lima juta rupiah) tambahan untuk setiap "
    "anggota keluarga sedarah dan keluarga semenda dalam garis keturunan lurus serta anak angkat, yang menjadi "
    "tanggungan sepenuhnya, paling banyak 3 (tiga) orang untuk setiap keluarga. Pasal 2 Besarnya biaya jabatan "
    "sebagaimana dimaksud ditetapkan sebesar 5% (lima persen) dari penghasilan bruto, paling banyak Rp7.200.000,00 "
    "(tujuh juta dua ratus ribu rupiah) setahun atau paling banyak Rp600.000,00 (enam ratus ribu rupiah) sebulan."
)


def sidik_data() -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(DATA_DIR.iterdir()) if p.is_file()}


@pytest.fixture(autouse=True)
def data_resmi_tidak_berubah():
    sebelum = sidik_data()
    yield
    assert sidik_data() == sebelum, "taxagent/taxes/pph21/data/ berubah"


@pytest.mark.parametrize(
    "kata,nilai",
    [
        ("lima puluh empat juta", 54_000_000), ("empat juta lima ratus ribu", 4_500_000), ("seratus juta", 100_000_000),
        ("lima miliar", 5_000_000_000), ("dua ratus lima puluh juta", 250_000_000), ("nol", 0), ("lima belas", 15),
        ("tiga puluh lima", 35), ("sebelas", 11), ("seribu", 1000), ("dua juta empat ratus ribu", 2_400_000),
    ],
)
def test_number_words(kata, nilai):
    assert parse_terbilang(kata) == nilai


def test_number_words_fractions_and_foreign_words():
    assert parse_terbilang("nol koma lima") == Decimal("0.5")
    assert parse_terbilang("lima juta rupiah dolar") is None


def test_rupiah_tolerates_spaces():
    assert parse_rupiah("100.000.000,00") == parse_rupiah("100 .000.000") == 100_000_000


def test_digits_not_matching_words_unused():
    t = PMK_2027.replace("Rp60.000.000,00 (enam puluh juta rupiah) untuk diri", "Rp60.000.000,00 (enam juta rupiah) untuk diri")
    b = clean_text(t)
    assert len(b.mismatches) == 1 and "6000000" in b.mismatches[0]
    h = extract_amounts(t)
    assert "ptkp" not in [x.key for x in h.findings] and h.mismatches


def test_all_scoped_keys_read_and_equal_verified_table():
    d = assemble_draft(2027, [extract_amounts(p.read_text(encoding="utf-8"), p.name) for p in DASAR], base_year=2024)
    teks_pasal = [k for k in IN_SCOPE if k != "ter_bulanan"]
    assert {p.key: p.status for p in d.comparisons} == {**dict.fromkeys(teks_pasal, "sama"),
                                                         "ter_bulanan": "tidak_ditemukan"}
    assert d.yaml_text is None and not d.mismatches and not d.notes


def test_quote_and_source_recorded():
    h = extract_amounts((F / "uu-7-2021-pasal-17.txt").read_text(encoding="utf-8"), "uu-7-2021")
    [t] = h.findings
    assert t.key == "tarif_pasal_17" and t.source == "uu-7-2021" and "ORANG PRIBADI DALAM NEGERI" in t.quote
    assert [r["persen"] for r in t.value] == [5, 15, 25, 30, 35]


def test_new_regulation_draft_holds_only_changed_keys():
    d = assemble_draft(2027, [extract_amounts(PMK_2027, "pmk-2027")])
    status = {p.key: p.status for p in d.comparisons}
    assert status["ptkp"] == status["biaya_jabatan"] == "berubah"
    assert all(s == "tidak_ditemukan" for k, s in status.items() if k not in ("ptkp", "biaya_jabatan"))
    draf = yaml.safe_load(d.yaml_text)
    assert set(draf) == {"meta", "ptkp", "biaya_jabatan"}
    assert draf["meta"]["terverifikasi"] is False and draf["meta"]["warisi_dari"] == base_year_for(2027)
    assert draf["ptkp"]["wajib_pajak_sendiri"] == 60_000_000
    assert draf["biaya_jabatan"] == {"persen": 5, "maksimal_sebulan": 600_000, "maksimal_setahun": 7_200_000}
    gabung = {**load_raw(draf["meta"]["warisi_dari"]), **{k: v for k, v in draf.items() if k != "meta"}}
    gabung["meta"] = draf["meta"]
    assert RateTable(gabung).ptkp["wajib_pajak_sendiri"] == 60_000_000
    assert "BELUM BERLAKU" in d.yaml_text and "| `ptkp` | **berubah**" in d.report


def test_conflicting_sources_become_conflict_and_skip_draft():
    lama = (F / "pmk-101-2016-pasal-1.txt").read_text(encoding="utf-8")
    d = assemble_draft(2027, [extract_amounts(lama, "pmk-101-2016"), extract_amounts(PMK_2027, "pmk-2027")])
    p = {x.key: x for x in d.comparisons}
    assert p["ptkp"].status == "konflik" and p["ptkp"].source == ["pmk-101-2016", "pmk-2027"]
    assert set(yaml.safe_load(d.yaml_text)) == {"meta", "biaya_jabatan"}


def test_partial_daily_ter_finding_keeps_other_sub_keys():
    t = (F / "pmk-168-2023-pasal-10-12.txt").read_text(encoding="utf-8").replace(
        "lebih dari Rp2.500.000,00 (dua juta lima ratus ribu rupiah", "lebih dari Rp3.000.000,00 (tiga juta rupiah"
    )
    d = assemble_draft(2027, [extract_amounts(t)], base_year=2024)
    draf = yaml.safe_load(d.yaml_text)
    lama = load_raw(2024)["ter_harian"]
    assert draf["ter_harian"] == {**lama, "batas_atas_ter_harian": 3_000_000}


def test_discontinuous_layers_rejected():
    t = (F / "pp-68-2009-pasal-4-5.txt").read_text(encoding="utf-8").replace(
        "di atas Rp100.000.000,00 (seratus juta rupiah) sampai dengan Rp500", "di atas Rp200.000.000,00 (dua ratus juta rupiah) sampai dengan Rp500"
    )
    h = extract_amounts(t)
    assert "pph_final_pesangon" not in [x.key for x in h.findings]
    assert any("tidak bersambung" in c for c in h.notes)


def test_honorarium_partial_rank_unused():
    t = (F / "pp-80-2010-pasal-4.txt").read_text(encoding="utf-8").split("c. sebesar 15%")[0]
    h = extract_amounts(t)
    assert not h.findings and any("golongan" in c for c in h.notes)


def test_year_with_existing_table_becomes_revision_proposal_without_touching_file():
    d = assemble_draft(2026, [extract_amounts(PMK_2027)])
    draf = yaml.safe_load(d.yaml_text)
    asli = yaml.safe_load((DATA_DIR / "tarif_2026.yaml").read_text(encoding="utf-8"))
    assert draf["meta"]["warisi_dari"] == asli["meta"]["warisi_dari"] and draf["meta"]["terverifikasi"] is False
    assert draf["meta"]["catatan_verifikasi"] == asli["meta"]["catatan_verifikasi"]
    assert draf["ptkp"]["wajib_pajak_sendiri"] == 60_000_000


def test_must_not_write_to_data_folder():
    d = assemble_draft(2027, [extract_amounts(PMK_2027)])
    for folder in (DATA_DIR, DATA_DIR / "sub", DATA_DIR / ".." / "data"):
        with pytest.raises(DraftRejected):
            write_draft(d, folder)
    assert not (DATA_DIR / "sub").exists()


def test_existing_draft_not_overwritten(tmp_path):
    d = assemble_draft(2027, [extract_amounts(PMK_2027)])
    a, b = write_draft(d, tmp_path)
    assert (a.name, b.name) == ("draf_tarif_2027.md", "draf_tarif_2027.yaml")
    b.write_text("diedit reviewer", encoding="utf-8")
    with pytest.raises(DraftRejected):
        write_draft(d, tmp_path)
    assert b.read_text(encoding="utf-8") == "diedit reviewer"


def test_draft_name_never_read_as_rate_table(tmp_path):
    assert not Path("draf_tarif_2027.yaml").match("tarif_*.yaml")


def test_cli_exit_code(tmp_path, capsys):
    sumber = tmp_path / "pmk-2027.txt"
    sumber.write_text(PMK_2027, encoding="utf-8")
    assert main(["draft-rates", "--year", "2027", "--source", str(sumber), "--output", str(tmp_path / "a")]) == 1
    assert (tmp_path / "a" / "draf_tarif_2027.yaml").exists()
    args = ["draft-rates", "--year", "2027", "--base-year", "2024", "--output", str(tmp_path / "b")]
    for p in DASAR:
        args += ["--source", str(p)]
    assert main(args) == 0
    assert not (tmp_path / "b" / "draf_tarif_2027.yaml").exists() and (tmp_path / "b" / "draf_tarif_2027.md").exists()
    assert main(["draft-rates", "--year", "2027", "--source", str(tmp_path / "tidak-ada.txt"), "--output", str(tmp_path / "c")]) == 3
    assert main(["draft-rates", "--year", "2027", "--source", str(sumber), "--output", str(DATA_DIR)]) == 3
    assert "DITOLAK" in capsys.readouterr().err


def test_natura_limit_now_data_and_not_held_as_logic():
    from taxagent.taxes.pph21.calc import load_rates
    from taxagent.update.gates import GateContext, check_gates

    assert load_rates(2025).natura["kupon_batas_sebulan"] == Decimal(2_000_000)
    teks = (F / "pmk-66-2023-pasal-5-lampiran-a.txt").read_text(encoding="utf-8").replace(
        "a. Rp2.000.000,00 (dua juta rupiah) untuk tiap Pegawai",
        "a. Rp2.500.000,00 (dua juta lima ratus ribu rupiah) untuk tiap Pegawai")
    d = assemble_draft(2027, [extract_amounts(teks, "pmk-66-ubah")], base_year=2024)
    natura = next(p for p in d.comparisons if p.key == "natura")
    assert natura.status == "berubah" and natura.new["kupon_batas_sebulan"] == 2500000
    g1 = next(g for g in check_gates(d, [extract_amounts(teks)], GateContext(phase1_keys=["natura"])) if g.code == "G1")
    assert g1.passed, g1.reasons


def test_g1_holds_a_changed_key_phase1_did_not_name():
    from taxagent.update.gates import GateContext, check_gates

    teks = (F / "pmk-66-2023-pasal-5-lampiran-a.txt").read_text(encoding="utf-8").replace(
        "a. Rp2.000.000,00 (dua juta rupiah) untuk tiap Pegawai",
        "a. Rp2.500.000,00 (dua juta lima ratus ribu rupiah) untuk tiap Pegawai")
    d = assemble_draft(2027, [extract_amounts(teks, "pmk-66-ubah")], base_year=2024)
    g1 = next(g for g in check_gates(d, [extract_amounts(teks)], GateContext(phase1_keys=["ptkp"])) if g.code == "G1")
    assert not g1.passed
    assert any("tidak disebut Fase 1" in r and "natura" in r for r in g1.reasons)
    no_context = next(g for g in check_gates(d, [extract_amounts(teks)], GateContext()) if g.code == "G1")
    assert not any("tidak disebut Fase 1" in r for r in no_context.reasons)
