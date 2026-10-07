from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from test_draft_gates import BERLAKU, JABATAN, PTKP

from taxagent.cli import main
from taxagent.monitor.storage import ImpactNote, MonitorState, save
from taxagent.update import assemble_draft, extract_amounts
from taxagent.update.amounts import format_rupiah, parse_terbilang, to_terbilang
from taxagent.update.assemble import Draft
from taxagent.update.evaluation import base_with, mutate_text, new_value
from taxagent.update.gates import GateContext, GateResult, effective_from_text
from taxagent.update.llm import excerpt, extract_llm, finding_leaves, groups_in_text, parse


class KlienPalsu:
    def __init__(self, jawaban: dict[str, list[dict]] | None = None, rusak: bool = False):
        self.jawaban, self.rusak, self.panggilan = jawaban or {}, rusak, []

    def __call__(self, sistem: str, pengguna: str, versi: str):
        kelompok = next(k for k in ("ptkp", "biaya_jabatan", "biaya_pensiun", "tarif_pasal_17", "bukan_pegawai",
                                    "ter_harian", "pph_final_pesangon", "pph_final_manfaat_pensiun",
                                    "pph_final_honorarium_pns") if f"\n{k}." in sistem or f"\n{k}[" in sistem)
        self.panggilan.append(kelompok)
        if self.rusak:
            return None, {"galat": "timeout"}
        return {"nilai": self.jawaban.get(kelompok, [])}, {"token_masuk": 100, "token_keluar": 10}


PTKP_BENAR = [
    {"field": "ptkp.wajib_pajak_sendiri", "nilai": 60000000, "kutipan": "a. Rp60.000.000,00 (enam puluh juta rupiah) untuk diri Wajib Pajak orang pribadi"},
    {"field": "ptkp.tambahan_kawin", "nilai": 5000000, "kutipan": "b. Rp5.000.000,00 (lima juta rupiah) tambahan untuk Wajib Pajak yang kawin"},
    {"field": "ptkp.tambahan_tanggungan", "nilai": 5000000, "kutipan": "d. Rp5.000.000,00 (lima juta rupiah) tambahan untuk setiap anggota keluarga"},
    {"field": "ptkp.maksimal_tanggungan", "nilai": 3, "kutipan": "paling banyak 3 (tiga) orang untuk setiap keluarga"},
]


def draf_llm(teks: str, klien, keys=None) -> Draft:
    h = extract_amounts(teks, "s")
    k = GateContext(keys, {"s": effective_from_text(teks, "s")}, llm=extract_llm(teks, klien), source_status={"s": []})
    return assemble_draft(2027, [h], context=k)


def g(d: Draft, kode: str) -> GateResult:
    return next(x for x in d.gates if x.code == kode)


def test_g4_both_extractors_agree_so_ready():
    d = draf_llm(PTKP + BERLAKU, KlienPalsu({"ptkp": PTKP_BENAR}))
    assert g(d, "G4").passed is True and d.decision == "siap", d.decision_reason


def test_g4_llm_reads_other_number_holds():
    salah = [dict(x) for x in PTKP_BENAR]
    salah[1] = {"field": "ptkp.tambahan_kawin", "nilai": 60000000,
                "kutipan": "a. Rp60.000.000,00 (enam puluh juta rupiah) untuk diri Wajib Pajak orang pribadi"}
    d = draf_llm(PTKP + BERLAKU, KlienPalsu({"ptkp": salah}))
    assert g(d, "G4").passed is False and d.decision == "tahan"
    assert any("tambahan_kawin" in a for a in g(d, "G4").reasons)


def test_g4_llm_misses_changed_number_holds():
    d = draf_llm(PTKP + BERLAKU, KlienPalsu({"ptkp": PTKP_BENAR[:2]}))
    assert g(d, "G4").passed is False and "tidak menemukan" in " ".join(g(d, "G4").reasons)


def test_g4_llm_sees_change_regex_missed_holds():
    teks = JABATAN.replace("Besarnya biaya jabatan sebagaimana dimaksud ditetapkan", "Biaya jabatan ditetapkan") + BERLAKU
    assert not finding_leaves([extract_amounts(teks)])
    klien = KlienPalsu({"biaya_jabatan": [{"field": "biaya_jabatan.maksimal_sebulan", "nilai": 600000,
                                           "kutipan": "atau paling banyak Rp600.000,00 (enam ratus ribu rupiah) sebulan"}]})
    d = draf_llm(teks, klien)
    assert not d.berubah and d.decision == "tahan" and g(d, "G4").passed is False


def test_g4_broken_llm_answer_holds():
    d = draf_llm(PTKP + BERLAKU, KlienPalsu(rusak=True))
    assert g(d, "G4").passed is False and d.decision == "tahan"


def test_parse_drops_made_up_quotes_missing_numbers_and_foreign_fields():
    teks = PTKP + BERLAKU
    h = parse({"nilai": [
        {"field": "ptkp.wajib_pajak_sendiri", "nilai": 60000000, "kutipan": "PTKP diri sendiri enam puluh juta rupiah setahun"},
        {"field": "ptkp.tambahan_kawin", "nilai": 6000000, "kutipan": "b. Rp5.000.000,00 (lima juta rupiah) tambahan untuk Wajib Pajak yang kawin"},
        {"field": "natura.batas", "nilai": 1, "kutipan": "paling banyak 3 (tiga) orang untuk setiap keluarga"},
        PTKP_BENAR[3],
    ]}, teks)
    assert list(h.values) == ["ptkp.maksimal_tanggungan"]
    assert len(h.dropped) == 3


def test_parse_two_different_answers_for_one_field_drops_both():
    teks = PTKP + BERLAKU
    h = parse({"nilai": [PTKP_BENAR[1], {**PTKP_BENAR[2], "field": "ptkp.tambahan_kawin", "nilai": 60000000,
                                         "kutipan": PTKP_BENAR[0]["kutipan"]}]}, teks)
    assert "ptkp.tambahan_kawin" not in h.values


def test_one_call_per_group_whose_terms_exist():
    teks = PTKP + JABATAN + BERLAKU
    assert groups_in_text(teks) == ["ptkp", "biaya_jabatan"]
    k = KlienPalsu()
    extract_llm(teks, k)
    assert k.panggilan == ["ptkp", "biaya_jabatan"]


def test_snippet_contains_term_and_is_bounded():
    teks = ("lorem ipsum " * 2000) + "Besarnya biaya jabatan 5% (lima persen)" + (" dolor" * 2000)
    c = excerpt(teks, ("biaya jabatan",), limit=2000)
    assert "biaya jabatan" in c and len(c) <= 2000 + 10


def _status(tmp_path: Path, kategori: str, keys: list[str], teks: str) -> Path:
    sumber = tmp_path / "pmk-baru.txt"
    sumber.write_text(teks, encoding="utf-8")
    c = ImpactNote(id_dokumen="x", identitas="PMK 9 Tahun 2026", judul="PENYESUAIAN BESARNYA PTKP", perihal="",
                   tanggal_feed="2026-12-01", first_seen="2026-12-01T21:00:00", kategori=kategori,
                   key_terdampak=keys, url_teks=str(sumber))
    berkas = tmp_path / "status.json"
    save(MonitorState(catatan=[c]), berkas)
    return berkas


def test_basis_note_becomes_draft_with_year_from_text(tmp_path, capsys):
    st = _status(tmp_path, "dasar", ["ptkp"], PTKP + BERLAKU)
    assert main(["draft-rates", "--note", "1", "--status", str(st), "--output", str(tmp_path / "o")]) == 1
    out = capsys.readouterr().out
    assert "Tahun pajak dari teks: 2027" in out and "Gerbang: tahan" in out
    assert (tmp_path / "o" / "draf_tarif_2027.yaml").exists()


def test_note_with_logic_key_held_g1(tmp_path):
    st = _status(tmp_path, "dasar", ["ptkp", "mekanisme_pemotongan"], PTKP + BERLAKU)
    main(["draft-rates", "--note", "1", "--status", str(st), "--output", str(tmp_path / "o")])
    md = (tmp_path / "o" / "draf_tarif_2027.md").read_text(encoding="utf-8")
    assert "| G1 lingkup dan struktur | **gagal** |" in md and "mekanisme_pemotongan" in md


def test_facility_note_makes_no_draft(tmp_path, capsys):
    st = _status(tmp_path, "fasilitas", [], PTKP + BERLAKU)
    assert main(["draft-rates", "--note", "1", "--status", str(st), "--output", str(tmp_path / "o")]) == 0
    assert "bukan perubahan angka" in capsys.readouterr().out and not (tmp_path / "o").exists()


def test_without_year_and_mid_year_effective_rejected(tmp_path, capsys):
    st = _status(tmp_path, "dasar", ["ptkp"], PTKP + "Pasal 3 Ketentuan ini mulai berlaku pada Masa Pajak Juli 2027. ")
    assert main(["draft-rates", "--note", "1", "--status", str(st), "--output", str(tmp_path / "o")]) == 3
    assert "beri --year" in capsys.readouterr().err


def test_without_source_and_note_rejected(tmp_path):
    assert main(["draft-rates", "--year", "2027", "--output", str(tmp_path / "o")]) == 3


@pytest.mark.parametrize("n", [0, 1, 11, 15, 99, 100, 110, 1000, 1320000, 2025000, 4500000, 54000000, 58500000,
                               150000, 5000000000, 168750])
def test_number_words_roundtrip(n):
    assert parse_terbilang(to_terbilang(n)) == n


def test_number_words_decimal():
    assert to_terbilang(Decimal("2.5")) == "dua koma lima" and parse_terbilang("dua koma lima") == Decimal("2.5")
    assert format_rupiah(54000000) == "Rp54.000.000,00"


def test_mutation_consistent_digits_and_words():
    t = "a. Rp 54.000.000,00 (lima puluh empat juta rupiah) untuk diri; tarif 5% (lima persen); paling banyak 3 (tiga) orang"
    m, n = mutate_text(t, Decimal(54000000), Decimal(64800000), "rupiah", "konsisten")
    assert n == 1 and "64.800.000,00 (enam puluh empat juta delapan ratus ribu rupiah)" in m
    m, _ = mutate_text(t, Decimal(54000000), Decimal(64800000), "rupiah", "digit")
    assert "64.800.000,00 (lima puluh empat juta rupiah)" in m
    m, _ = mutate_text(t, Decimal(5), Decimal(6), "persen", "kata")
    assert "5% (enam persen)" in m
    m, _ = mutate_text(t, Decimal(3), Decimal(4), "orang", "konsisten")
    assert "paling banyak 4 (empat) orang" in m
    assert extract_amounts(mutate_text(t, Decimal(54000000), Decimal(64800000), "rupiah", "digit")[0]).mismatches


def test_mutation_leaves_numbers_containing_old_number():
    m, n = mutate_text("Rp154.000.000,00 (seratus lima puluh empat juta rupiah) dan 25% (dua puluh lima persen)",
                       Decimal(54000000), Decimal(1), "rupiah", "konsisten")
    assert n == 0 and "154.000.000" in m
    assert mutate_text("25% (dua puluh lima persen)", Decimal(5), Decimal(6), "persen", "konsisten")[1] == 0


def test_new_value_and_dasar_dengan():
    assert new_value(Decimal(2025000), "rupiah", False) == Decimal(2430000)
    assert new_value(Decimal(0), "persen", False) == 1 and new_value(Decimal(0), "persen", True) is None
    raw = base_with({"tarif_pasal_17[0].batas_atas": Decimal(25000000), "tarif_pasal_17[1].batas_atas": None,
                     "tarif_pasal_17[1].persen": Decimal(35), "ptkp.wajib_pajak_sendiri": Decimal(2880000)})
    assert len(raw["tarif_pasal_17"]) == 2 and raw["tarif_pasal_17"][1] == {"batas_atas": None, "persen": 35}
    assert raw["ptkp"]["wajib_pajak_sendiri"] == 2880000 and raw["ptkp"]["tambahan_kawin"] == 4500000


def test_other_numbers_with_words_also_checked():
    from taxagent.update.amounts import clean_text

    b = clean_text("tanggungan paling banyak 3 (empat) orang; jangka waktu 4 (empat) bulan; ayat (1) dan Pasal 7 (1)")
    assert len(b.mismatches) == 1 and "3" in b.mismatches[0] and Decimal(4) in b.verified
