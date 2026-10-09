import importlib.util
from pathlib import Path

from taxagent.monitor.relation_llm import Evidence, Relation

_f = Path(__file__).resolve().parents[1] / "pipeline" / "relation_remaining_llm.py"
_spec = importlib.util.spec_from_file_location("relation_remaining_llm", _f)
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)

INDEKS = M.number_index({"KEPPRES 188 Tahun 1998", "PER-36/BC/2016", "PER-5/PP/2008", "KMK 24/EF2/2026",
                         "KMK 24/BC/2026", "KEP-1/SA8/2019", "KMK 433/KMK05/1978", "KMK 433/KMK04/1978"})


def _r(jp, nomor, tahun, klausa):
    return Relation("mencabut", jp, nomor, tahun, "x", bukti=Evidence(0, len(klausa), klausa, "batang_tubuh"))


def test_kind_from_clause_phrase():
    r = _r("KEP", 188, 1998, "Keputusan Presiden Nomor 188 Tahun 1998 tentang Tata Cara dicabut")
    assert M.target_key(r, INDEKS) == "KEPPRES 188 Tahun 1998"
    r = _r("PER", 5, 2008, "Peraturan Kepala Badan Pendidikan dan Pelatihan Keuangan Nomor 5/PP/2008 dicabut")
    assert M.target_key(r, INDEKS) == "PER-5/PP/2008"


def test_written_unit_must_equal_key_unit():
    r = _r("PER", 36, 2016, "Peraturan Direktur Jenderal Perbendaharaan Nomor PER-36/PB/2016 tentang Pedoman")
    assert M.target_key(r, INDEKS) is None
    r = _r("KMK", 24, 2026, "Lampiran Keputusan Menteri Keuangan Nomor 24/MK/BC/2026 tentang Daftar Barang")
    assert M.target_key(r, INDEKS) == "KMK 24/BC/2026"
    r = _r("KEP", 1, 2019, "Keputusan Kepala Badan Kebijakan Fiskal Nomor 1/KF.2019 tentang Penetapan")
    assert M.target_key(r, INDEKS) is None
    r = _r("KMK", 433, 1978, "Keputusan Menteri Keuangan Nomor 433/KMK.05/1978 dinyatakan tidak berlaku")
    assert M.target_key(r, INDEKS) == "KMK 433/KMK05/1978"


def test_own_document_and_other_minister_not_target_kind():
    indeks = M.number_index({"PP 11 Tahun 2019", "PMK 11 Tahun 2019"})
    r = _r("PER", 11, 2019, "Pada saat Peraturan Pemerintah ini mulai berlaku, Peraturan Menteri Pekerjaan Umum dan "
                            "Perumahan Rakyat Nomor 11/PRT/M/2019 tentang Sistem dicabut")
    assert M.target_key(r, indeks) is None
    r = _r("PMK", 11, 2019, "Pada saat Peraturan Menteri ini mulai berlaku, Peraturan Menteri Keuangan Nomor "
                            "11/PMK.03/2019 tentang Tata Cara dicabut")
    assert M.target_key(r, indeks) == "PMK 11 Tahun 2019"
