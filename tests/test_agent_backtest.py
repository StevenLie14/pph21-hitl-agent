from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from taxagent.evaluation import agent_backtest as A
from taxagent.taxes.pph21 import tools as T
from taxagent.taxes.pph21.calc import rates


class Graf:
    def __init__(self):
        self.calls = []

    def query(self, cypher, **p):
        self.calls.append((cypher, p))
        if "faq" in cypher.lower():
            return [{"id": "faq#1"}]
        if "ks" in p:
            return [{"kunci": k} for k in p["ks"]]
        if "k" in p:
            return [{"kunci": p["k"], "judul": "x"}]
        return [{"kunci": "PMK 101 Tahun 2016", "rujukan": [{"kunci": "PMK 122 Tahun 2015"}]},
                {"kunci": "PMK 122 Tahun 2015", "rujukan": []}]


ISSUED = {"PMK 101 Tahun 2016": dt.date(2016, 6, 22), "PMK 122 Tahun 2015": dt.date(2015, 6, 29)}


def test_frozen_graph_hides_later_regulations_and_faq():
    g = A.FrozenGraph(Graf(), dt.date(2016, 6, 22), ISSUED)
    assert g.query("MATCH (p:Regulation) RETURN p") == [{"kunci": "PMK 122 Tahun 2015", "rujukan": []}]
    assert g.query("MATCH (p:Regulation {key: $k}) RETURN p", k="PMK 101 Tahun 2016") == []
    assert g.query("UNWIND $ks AS k RETURN k", ks=["PMK 101 Tahun 2016", "PMK 122 Tahun 2015"]) == [
        {"kunci": "PMK 122 Tahun 2015"}]
    assert g.query("CALL db.index.fulltext.queryNodes('faq_text', $q)", q="x") == []
    later = A.FrozenGraph(Graf(), dt.date(2016, 6, 23), ISSUED)
    assert len(later.query("MATCH (p:Regulation) RETURN p")) == 2


def test_answer_numbers_and_outcome_labels():
    assert A.answer_numbers("PPh setahun **Rp11.650.000**, PTKP Rp63.000.000,00; 5%") == {11_650_000, 63_000_000}
    r = A.PhaseRun("a", "basi_lanjutan", 1, "q", angka_lama=True)
    assert A.outcome(r) == "angka_lama_diam"
    r = A.PhaseRun("a", "sadar", 1, "q", angka_lama=True, tanggapi_klaim=True)
    assert A.outcome(r) == "angka_lama_dengan_catatan"
    r = A.PhaseRun("a", "sadar", 1, "q", angka_lama=True, melapor=True)
    assert A.outcome(r) == "melapor_dengan_angka"
    r = A.PhaseRun("a", "teradaptasi_ubah", 1, "q", angka_asli_di_ubah=True)
    assert A.outcome(r) == "ingatan"
    assert A.outcome(A.PhaseRun("a", "teradaptasi_asli", 1, "q", angka_benar=True)) == "benar"


def _table_2016(ptkp: int, sources: dict | None = None) -> dict:
    raw = rates.load_raw(2024)
    raw = {**raw, "ptkp": {**raw["ptkp"], "wajib_pajak_sendiri": ptkp}}
    return A._table(raw, 2016, ["uji"], sources)


def test_world_redirects_rate_tables_and_restores():
    case = {"jenis": "tahunan", "tahun": 2016}
    with A.world({2016: _table_2016(54_000_000)}, dt.date(2016, 6, 23)):
        assert rates.available_years() == [2016]
        assert A.engine_result(case, 2016) == Decimal("10650000")
    with A.world({2016: _table_2016(36_000_000)}, dt.date(2016, 6, 22)):
        assert A.engine_result(case, 2016) == Decimal("13350000")
    assert 2016 not in rates.available_years()
    with pytest.raises(rates.TaxYearNotAvailable):
        rates.load_rates(2016)


def test_frozen_regulation_map_drops_summaries_and_later_references():
    m = A.frozen_regulations(dt.date(2016, 6, 22), ISSUED)["topik"]["ptkp"]
    assert m["ringkasan"] == "" and m["rujukan"] == ["UU PPh Pasal 7 ayat (1)"]


def test_legal_basis_follows_tax_year_and_table_sources():
    kw = {"gaji_pokok": 15_000_000, "nilai_per_bulan": True, "status_ptkp": "K/1", "tahun_pajak": 2016}
    with A.world({2016: _table_2016(54_000_000, {"ptkp": "PMK 101 Tahun 2016"})}, dt.date(2016, 6, 23)):
        h = T.calculate_pph21_permanent_annual(**kw)
    assert "PMK No. 168 Tahun 2023" not in h["dasar_hukum"]
    assert "UU PPh Pasal 17 ayat (1) huruf a" in h["dasar_hukum"]
    assert "PMK 101 Tahun 2016" in h["dasar_hukum"] and h["dasar_hukum_nilai"] == {"ptkp": "PMK 101 Tahun 2016"}
    h = T.calculate_pph21_permanent_annual(**{**kw, "tahun_pajak": 2024})
    assert "PMK No. 168 Tahun 2023" in h["dasar_hukum"] and "dasar_hukum_nilai" not in h


def test_agent_reports_regulation_the_graph_does_not_know(monkeypatch, tmp_path):
    pytest.importorskip("langchain_core")
    from langchain_core.messages import AIMessage, SystemMessage

    from taxagent.agent import runner as R
    from taxagent.tools import regulation_graph as G

    class LLM:
        def __init__(self):
            self.seen = []

        def invoke(self, messages, **_):
            self.seen.append(list(messages))
            return AIMessage(content="PPh 21 setahun Rp14.800.000.")

    monkeypatch.setenv("PPH21_PERMINTAAN_AGENT", str(tmp_path / "permintaan.jsonl"))
    monkeypatch.setattr("taxagent.tools.registry.graph_enabled", lambda: True)
    llm = LLM()
    agent, other = R.TaxAgent(llm=llm), R.TaxAgent(llm=LLM())
    monkeypatch.setattr(G, "find_regulation", lambda regulation, date="": {
        "berhasil": False, "galat": f"'{regulation}' tidak ada di graf."})
    monkeypatch.setattr(G, "check_citations", lambda answer, results, d: [])
    p = agent.ask("Saya baca PMK No. 101/PMK.010/2016 menaikkan PTKP. Hitung PPh 21 2016.")
    auto = [j for j in p.trace if j.name == "report_possibly_stale"]
    assert len(auto) == 1 and auto[0].arguments["otomatis"] and auto[0].result["berhasil"]
    assert auto[0].arguments["regulation"] == "PMK 101 Tahun 2016"
    assert (tmp_path / "permintaan.jsonl").read_text(encoding="utf-8").count("peraturan_tidak_dikenal") == 1
    assert any(isinstance(m, SystemMessage) and "PMK 101 Tahun 2016" in m.content for m in llm.seen[0][1:])
    assert p.answer.startswith("PPh 21 setahun Rp14.800.000.") and "belum ada di data sistem" in p.answer
    monkeypatch.setattr(G, "find_regulation", lambda regulation, date="": {"berhasil": True, "peraturan": [{}]})
    p = other.ask("Hitung PPh 21 menurut PMK 168 Tahun 2023.")
    assert not p.trace and "belum ada di data sistem" not in p.answer


def test_calculation_args_for_other_case_kinds():
    name, kw = A.calculation_args({"jenis": "pensiunan_tahunan", "gaji": 6_000_000, "status": "K/2"}, 2013)
    assert name == "calculate_pph21_pensioner_annual" and kw["uang_pensiun"] == 6_000_000 and kw["nilai_per_bulan"]
    name, kw = A.calculation_args({"jenis": "bukan_pegawai", "gaji": 150_000_000}, 2022)
    assert name == "calculate_pph21_non_employee" and kw["penghasilan_bruto"] == 150_000_000
    name, kw = A.calculation_args({"jenis": "final", "jenis_final": "honorarium_pns", "golongan": "III",
                                   "gaji": 10_000_000}, 2011)
    assert name == "calculate_pph21_final" and kw["jenis"] == "honorarium_pns" and kw["golongan"] == "III"
    with pytest.raises(ValueError):
        A.calculation_args({"jenis": "harian"}, 2016)


def test_default_questions_for_other_case_kinds():
    q = A.question({"tahun": 2010, "jenis": "final", "jenis_final": "pesangon", "gaji": 120_000_000})
    assert "pesangon" in q and "Rp120.000.000" in q and "2010" in q
    q = A.question({"tahun": 2013, "jenis": "pensiunan_tahunan", "gaji": 6_000_000, "status": "K/2",
                    "status_teks": "kawin, 2 tanggungan"})
    assert "pensiunan" in q and "Rp6.000.000" in q


def test_partial_case_runs_only_adapted_phases_and_is_summarised_apart(monkeypatch):
    import contextlib
    from types import SimpleNamespace

    from taxagent.update import backtest as B
    from taxagent.update import evaluation as E

    monkeypatch.setattr(B, "load_events", lambda: [])
    monkeypatch.setattr(B, "documents", lambda *a: {})
    monkeypatch.setattr(E, "load_labels", lambda: {})
    plan = SimpleNamespace(adapted={}, stale={}, adapted_ubah={"x": 1}, events=["PP 68 Tahun 2009"],
                           freeze=dt.date(2009, 11, 16), adapted_cut=dt.date(2009, 11, 17), patch_source="manusia",
                           keys_reviewed=1, lead_days=46)
    monkeypatch.setattr(A, "plan_case", lambda *a: plan)
    monkeypatch.setattr(A, "_table", lambda *a, **k: {})
    monkeypatch.setattr(A, "world", lambda *a, **k: contextlib.nullcontext())
    monkeypatch.setattr(A, "phase_world", lambda p, ph: ({}, p.freeze))
    values = iter([Decimal(5_500_000), None] * 2 + [Decimal(5_500_000), Decimal(4_200_000)] * 2)
    monkeypatch.setattr(A, "engine_result", lambda case, y: next(values))

    class Agent:
        def ask(self, q):
            return SimpleNamespace(answer="PPh 21 Rp4.200.000", trace=[], rounds=1, citation_corrections=[],
                                   tokens_in=100, tokens_out=7)

    full = {"id": "k1", "tahun": 2010, "jenis": "final", "jenis_final": "pesangon", "gaji": 1, "klaim": "",
            "disebut": "x", "peristiwa": []}
    partial = {**full, "id": "k2", "fase": ["teradaptasi_asli", "teradaptasi_ubah"], "sebagian": True}
    h = A.run([full, partial], Agent, None, [], repeats=1)
    phases = {r["kasus"]: [] for r in h["run"]}
    for r in h["run"]:
        phases[r["kasus"]].append(r["fase"])
    assert phases["k2"] == ["teradaptasi_asli", "teradaptasi_ubah"]
    assert set(phases["k1"]) == set(A.PHASES)
    assert set(h["ringkasan_sebagian"]) == {"teradaptasi_asli", "teradaptasi_ubah"}
    assert h["ringkasan"]["teradaptasi_asli"]["n"] == 1
    assert h["token"] == {"masuk": 700, "keluar": 49, "keluar_per_run": 7.0}
    assert "kasus sebagian" in A.markdown_report(h, {})
