from __future__ import annotations

import pytest

from taxagent.monitor.memory_graph import from_texts
from taxagent.tools import regulation_graph as G
from taxagent.update import assemble_draft, extract_amounts
from taxagent.update.gates import GateContext, effective_from_text
from taxagent.update.graph_updater import keys_from_graph
from taxagent.update.source_status import status_from_graph

REPEAL = ("Pasal 1 Pada saat Peraturan Menteri ini mulai berlaku, Peraturan Menteri Keuangan Nomor 168 Tahun 2023 "
          "tentang Petunjuk Pelaksanaan Pemotongan Pajak atas Penghasilan sehubungan dengan Pekerjaan, Jasa, atau "
          "Kegiatan Orang Pribadi dicabut dan dinyatakan tidak berlaku. Pasal 2 Peraturan Menteri ini mulai berlaku "
          "pada tanggal 1 Januari 2028. ")
OLD = "PMK 168 Tahun 2023"
NEW = "PMK 99 Tahun 2027"


@pytest.fixture()
def repeal_graph():
    docs = {OLD: {"teks": "Pasal 2 biaya jabatan ...", "mulai": "2024-01-01"},
            NEW: {"teks": REPEAL, "mulai": "2028-01-01"}}
    rel = [{"dari": NEW, "jenis": "mencabut", "ke": OLD, "tgl_efektif": "2028-01-01"}]
    defs = [(OLD, "biaya_jabatan", ["2"]), (OLD, "ter_bulanan", ["3"])]
    G.use_client(from_texts(docs, rel, defs))
    yield
    G.use_client(None)


def test_graph_status_follows_the_repeal_date(repeal_graph):
    before = G.find_regulation(regulation=OLD, date="2027-06-01")["peraturan"][0]
    after = G.find_regulation(regulation=OLD, date="2028-06-01")["peraturan"][0]
    assert before["status"] not in ("dicabut", "berakhir")
    assert after["status"] == "dicabut" and after["oleh"] == [NEW]


def test_every_parameter_of_the_repealed_basis_is_a_candidate(repeal_graph):
    keys, trace = keys_from_graph(NEW)
    assert keys == ["biaya_jabatan", "ter_bulanan"] and all(t.startswith(f"mencabut {OLD}") for t in trace)


def test_repeal_only_text_is_held_by_g1(repeal_graph):
    keys, _ = keys_from_graph(NEW)
    d = assemble_draft(2028, [extract_amounts(REPEAL, NEW)],
                       context=GateContext(keys, {NEW: effective_from_text(REPEAL, NEW)}, source_status={NEW: []}))
    g = {x.code: x for x in d.gates}
    assert not d.berubah and d.decision == "tahan"
    assert g["G1"].passed is False and "tidak terbaca" in g["G1"].reasons[0]


def test_draft_from_the_repealed_source_is_held_by_g8(repeal_graph):
    status = status_from_graph(OLD)
    assert status == [("MENCABUT", NEW)]
    text = ("Pasal 2 Besarnya biaya jabatan ditetapkan sebesar 5% (lima persen) dari penghasilan bruto, paling banyak "
            "Rp7.200.000,00 (tujuh juta dua ratus ribu rupiah) setahun atau paling banyak Rp600.000,00 (enam ratus "
            "ribu rupiah) sebulan. Pasal 3 Ketentuan ini mulai berlaku pada Tahun Pajak 2028. ")
    d = assemble_draft(2028, [extract_amounts(text, OLD)],
                       context=GateContext(None, {OLD: effective_from_text(text, OLD)}, source_status={OLD: status}))
    assert {x.code: x for x in d.gates}["G8"].passed is False and d.decision == "tahan"


CALC = {"gaji_pokok": 15_000_000, "status_ptkp": "K/1", "kutipan_status_ptkp": "K/1", "masa_pajak": 3,
        "tahun_pajak": 2025}


def _agent_with(monkeypatch, tmp_path, basis, answer):
    pytest.importorskip("langchain_core")
    from langchain_core.messages import AIMessage

    from taxagent.agent import runner as R

    class LLM:
        def __init__(self):
            self.seen = []
            self.replies = [AIMessage(content="", tool_calls=[
                {"name": "calculate_pph21_permanent_monthly", "args": CALC, "id": f"c{i}"} for i in range(2)]),
                AIMessage(content=answer)]

        def invoke(self, messages, **_):
            self.seen.append(list(messages))
            return self.replies.pop(0) if self.replies else AIMessage(content=answer)

    monkeypatch.setenv("PPH21_PERMINTAAN_AGENT", str(tmp_path / "permintaan.jsonl"))
    monkeypatch.setattr("taxagent.tools.registry.graph_enabled", lambda: True)
    monkeypatch.setattr("taxagent.taxes.pph21.tools._basis_status", lambda result, kw: basis)
    monkeypatch.setattr("taxagent.taxes.pph21.tools._locations", lambda refs: None)
    monkeypatch.setattr(G, "check_citations", lambda answer, results, d: [])
    llm = LLM()
    return R.TaxAgent(llm=llm), llm


def test_agent_reports_a_repealed_basis_by_code(monkeypatch, tmp_path, repeal_graph):
    basis = [{"peraturan": OLD, "status": "dicabut", "pada": "2028-06-01", "oleh": [NEW]}]
    agent, llm = _agent_with(monkeypatch, tmp_path, basis, "PPh 21 Maret Rp1.000.000.")
    p = agent.ask("Hitung PPh 21 gaji Rp15 juta, status saya K/1.")
    auto = [j for j in p.trace if j.name == "report_possibly_stale"]
    assert len(auto) == 1 and auto[0].arguments["otomatis"] and auto[0].result["berhasil"]
    assert auto[0].arguments["reason"] == "dasar_hukum_tidak_berlaku" and auto[0].arguments["regulation"] == OLD
    log = (tmp_path / "permintaan.jsonl").read_text(encoding="utf-8")
    assert log.count("dasar_hukum_tidak_berlaku") == 1 and NEW in log
    calc = next(j for j in p.trace if j.name == "calculate_pph21_permanent_monthly")
    assert OLD in calc.result["peringatan_dasar_hukum"]
    assert "sudah tidak berlaku menurut graf" in p.answer and OLD in p.answer


def test_basis_in_force_adds_no_note(monkeypatch, tmp_path, repeal_graph):
    basis = [{"peraturan": OLD, "status": "berlaku", "pada": "2025-12-31", "oleh": []}]
    agent, _ = _agent_with(monkeypatch, tmp_path, basis, "PPh 21 Maret Rp1.000.000.")
    p = agent.ask("Hitung PPh 21 gaji Rp15 juta, status saya K/1.")
    assert not [j for j in p.trace if j.name == "report_possibly_stale"]
    assert "sudah tidak berlaku menurut graf" not in p.answer


def test_note_stays_when_the_answer_names_the_repealed_basis(monkeypatch, tmp_path, repeal_graph):
    basis = [{"peraturan": OLD, "status": "dicabut", "pada": "2028-06-01", "oleh": [NEW]}]
    agent, _ = _agent_with(monkeypatch, tmp_path, basis, f"PPh 21 Maret Rp1.000.000. Dasar hukum: {OLD}.")
    p = agent.ask("Hitung PPh 21 gaji Rp15 juta, status saya K/1.")
    assert [j for j in p.trace if j.name == "report_possibly_stale"]
    assert p.answer.count("sudah tidak berlaku menurut graf") == 1


def test_basis_status_is_read_at_the_end_of_the_period_computed() -> None:
    import datetime as dt

    from taxagent.tools.registry import period_end

    assert period_end({"tahun_pajak": 2025, "masa_pajak": 3}, {}) == dt.date(2025, 3, 31)
    assert period_end({}, {"tahun_pajak": 2024, "masa_pajak": 2}) == dt.date(2024, 2, 29)
    assert period_end({"tahun_pajak": 2025, "masa_pajak": 12}, {}) == dt.date(2025, 12, 31)
    assert period_end({"tahun_pajak": 2025}, {}) == dt.date(2025, 12, 31)
    assert period_end({"tahun_pajak": 2025, "masa_pajak": "x"}, {}) == dt.date(2025, 12, 31)
    assert period_end({"tahun_pajak": dt.date.today().year + 2}, {}) == dt.date.today()
