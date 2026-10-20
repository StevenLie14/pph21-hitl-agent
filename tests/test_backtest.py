import copy
import datetime as dt
from decimal import Decimal

from taxagent.update.backtest import _shifted, documents, load_events, stale_table, table_gaps
from taxagent.update.evaluation import load_labels
from taxagent.update.gates import Effective, effective_year


def _docs():
    return documents(load_events(), load_labels())


def test_stale_table_knows_only_earlier_regulations():
    docs = _docs()
    before_2016 = stale_table(docs, dt.date(2016, 6, 22))
    assert before_2016["ptkp"]["wajib_pajak_sendiri"] == 36000000
    after_uu36 = stale_table(docs, dt.date(2012, 10, 22))
    assert [r["persen"] for r in after_uu36["tarif_pasal_17"]] == [5, 15, 25, 30]


def test_stale_table_leaves_unknown_values_out():
    docs = _docs()
    t = stale_table(docs, dt.date(2005, 1, 31))
    assert "batas_bebas_harian" not in t["ter_harian"]
    assert "lapisan" in t["ter_harian"]
    assert not t.get("biaya_jabatan")


def test_events_use_inline_values_when_not_labelled():
    docs = _docs()
    assert docs["UU 36 Tahun 2008"]["nilai"]["ptkp.wajib_pajak_sendiri"] == Decimal(15840000)
    assert {d["peran"] for d in docs.values()} == {"awal", "peristiwa", "tanpa_perubahan", "kontrol_negatif"}


def test_shifted_effective_keeps_mid_year_and_transition():
    whole = _shifted(Effective("s", applies_to=["TAHUN PAJAK 2016"]), 11)
    assert effective_year(whole)[0] == 2027
    mid = _shifted(Effective("s", start="2016-06-27"), 11)
    assert effective_year(mid)[0] is None
    assert _shifted(Effective("s", transitional=True), 5).transitional


def test_cumulative_start_table_holds_only_the_initial_regulations():
    docs = _docs()
    start = stale_table(docs, dt.date.max, roles={"awal"})
    first_event = min(i["tanggal"] for i in docs.values() if i["peran"] != "awal")
    assert table_gaps(start, stale_table(docs, first_event)) == []
    assert table_gaps(start, stale_table(docs, dt.date.max))


def test_table_gaps_names_missing_and_wrong_leaves():
    docs = _docs()
    truth = stale_table(docs, dt.date.max)
    own = copy.deepcopy(truth)
    own["ptkp"]["wajib_pajak_sendiri"] = 1
    own["biaya_jabatan"] = None
    gaps = table_gaps(own, truth)
    assert "ptkp.wajib_pajak_sendiri" in gaps
    assert any(g.startswith("biaya_jabatan") for g in gaps)
