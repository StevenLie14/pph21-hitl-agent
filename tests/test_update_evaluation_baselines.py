from decimal import Decimal
from types import SimpleNamespace

from taxagent.update.evaluation import Case, _llm_wrong, _score_case, summarize_mutations


def _draft(decision, changed, failed):
    gates = [SimpleNamespace(code=g, passed=False, reasons=[]) for g in failed]
    return SimpleNamespace(decision=decision, gates=gates, berubah=changed)


def _cmp(key, new):
    return SimpleNamespace(key=key, new=new)


EXPECTED = {"biaya_jabatan": {"persen": 5, "maks_bulanan": 500000}}


def test_wrong_draft_held_by_one_gate_is_counted_for_baselines():
    c = Case("PMK x", "uji", "digit")
    _score_case(c, _draft("tahan", [_cmp("biaya_jabatan", {"persen": 5, "maks_bulanan": 600000})], ["G3"]), EXPECTED)
    assert c.draf_salah and not c.salah_lolos and c.penahan_tunggal == "G3"


def test_right_ready_draft_is_not_a_baseline_error():
    c = Case("PMK x", "uji", "ubah")
    _score_case(c, _draft("siap", [_cmp("biaya_jabatan", {"persen": 5, "maks_bulanan": 500000})], []), EXPECTED)
    assert not c.draf_salah and not c.salah_lolos and not c.penahan_tunggal


def test_llm_alone_wrong_only_on_values_it_read():
    llm = SimpleNamespace(values={"biaya_jabatan.maks_bulanan": Decimal(600000)})
    assert _llm_wrong(llm, EXPECTED)
    assert not _llm_wrong(SimpleNamespace(values={"biaya_jabatan.persen": Decimal(5)}), EXPECTED)
    assert not _llm_wrong(SimpleNamespace(values={}), EXPECTED)
    assert not _llm_wrong(None, EXPECTED)


def test_summary_counts_baselines():
    cases = [
        {"set": "uji", "jenis": "digit", "keputusan": "tahan", "salah_lolos": False, "menahan": ["G3"],
         "draf_salah": True, "llm_salah": False, "penahan_tunggal": "G3"},
        {"set": "uji", "jenis": "digit", "keputusan": "tahan", "salah_lolos": False, "menahan": ["G3", "G4"],
         "draf_salah": True, "llm_salah": True, "penahan_tunggal": ""},
    ]
    r = summarize_mutations(cases)["uji"]["digit"]
    assert r["draf_salah"] == 2 and r["llm_salah"] == 1 and r["tunggal_G3"] == 1 and r["sepakat_saja_lolos"] == 1
