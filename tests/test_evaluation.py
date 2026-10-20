from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from taxagent.evaluation import load_cases, matches, reference_result, run_cases, score_case, summarize
from taxagent.taxes.pph21.calc.rates import DATA_DIR
from taxagent.tools import TOOL_SPECS, all_tool_names, call_tool

KASUS = load_cases()
HOLDOUT = load_cases(DATA_DIR / "kasus_agent_holdout.yaml")
SKEMA = {fn.__name__: args for fn, args, _ in TOOL_SPECS}


@dataclass
class Jejak:
    name: str
    arguments: dict
    result: dict


@dataclass
class AgentTurn:
    answer: str = ""
    trace: list = field(default_factory=list)
    rounds: int = 1


def _panggil(nama: str, **argumen) -> Jejak:
    return Jejak(nama, argumen, call_tool(nama, **argumen))


@pytest.mark.parametrize("kasus", KASUS + HOLDOUT, ids=[k["id"] for k in KASUS + HOLDOUT])
def test_dataset_consistent_with_tool_schema(kasus):
    if kasus["perilaku"] in ("hitung", "info"):
        assert kasus["tool"] in all_tool_names()
    if kasus["perilaku"] != "hitung":
        return
    field_sah = set(SKEMA[kasus["tool"]].model_fields)
    assert set(kasus["argumen"]) <= field_sah, set(kasus["argumen"]) - field_sah
    assert set(kasus.get("argumen_dinilai", [])) <= set(kasus["argumen"])
    assert reference_result(kasus)["berhasil"]


def test_dataset_ids_unique():
    ids = [k["id"] for k in KASUS + HOLDOUT]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize(
    "harapan,aktual,cocok",
    [
        (15000000, 15000000.0, True),
        (15000000, "15000000", True),
        (15000000, 15000001, False),
        ("K/1", "k/1 ", True),
        ("K/1", "K/2", False),
        (True, True, True),
        (True, "true", True),
        (False, None, False),
        (True, 1, False),
    ],
)
def test_same(harapan, aktual, cocok):
    assert matches(harapan, aktual) is cocok


def _kasus(id_):
    return next(k for k in KASUS if k["id"] == id_)


def test_calculate_correct_after_ptkp_lookup():
    k = _kasus("pt-ter-01")
    p = AgentTurn(
        trace=[
            _panggil("lookup_ptkp", kawin=True, jumlah_tanggungan=1, tahun_pajak=2025),
            _panggil("calculate_pph21_permanent_monthly", **k["argumen"]),
        ]
    )
    h = score_case(k, p, 1.0, reference_result(k))
    assert h.tool_benar and h.tool_benar_percobaan_pertama
    assert h.argumen_benar and h.angka_benar and h.perilaku_benar
    assert h.field_benar == h.field_total == 4


def test_calculate_wrong_ptkp_status_caught_in_arguments_and_numbers():
    k = _kasus("pt-ter-02")
    salah = dict(k["argumen"], status_ptkp="K/3")
    h = score_case(k, AgentTurn(trace=[_panggil(k["tool"], **salah)]), 1.0, reference_result(k))
    assert h.tool_benar
    assert not h.argumen_benar and "status_ptkp" in h.argumen_salah
    assert not h.angka_benar and not h.perilaku_benar


def test_wrong_tool_then_fixed_counts_final_correct_but_first_attempt_wrong():
    k = _kasus("dk-01")
    p = AgentTurn(
        trace=[
            _panggil("calculate_pph21_non_employee", penghasilan_bruto=60000000, tahun_pajak=2024),
            _panggil(k["tool"], **k["argumen"]),
        ]
    )
    h = score_case(k, p, 1.0, reference_result(k))
    assert h.tool_benar and not h.tool_benar_percobaan_pertama and h.perilaku_benar


def test_default_field_counts_as_filled_when_model_omits_it():
    k = _kasus("pt-ter-05")
    tanpa = {x: v for x, v in k["argumen"].items() if x != "punya_npwp"}
    h = score_case(k, AgentTurn(trace=[_panggil(k["tool"], **tanpa)]), 1.0, reference_result(k))
    assert h.argumen_salah["punya_npwp"] == {"harapan": False, "aktual": True}
    assert not h.perilaku_benar


def test_clarification_correct_without_calculation_tool():
    k = _kasus("tb-01")
    h = score_case(k, AgentTurn(answer="Status PTKP dan masa pajaknya apa?"), 1.0, None)
    assert h.perilaku_benar


def test_clarification_wrong_when_model_guesses_and_calculates():
    k = _kasus("tb-01")
    tebak = _panggil(
        "calculate_pph21_permanent_monthly",
        gaji_pokok=10000000, status_ptkp="TK/0", masa_pajak=1, tahun_pajak=2025,
    )
    h = score_case(k, AgentTurn(trace=[tebak]), 1.0, None)
    assert not h.perilaku_benar


def test_refusal_still_correct_when_calculation_attempt_rejected_by_tool():
    k = _kasus("tl-03")
    gagal = _panggil(
        "calculate_pph21_permanent_monthly",
        gaji_pokok=15000000, status_ptkp="K/I/1", masa_pajak=3, tahun_pajak=2025,
    )
    assert gagal.result["berhasil"] is False
    h = score_case(k, AgentTurn(trace=[gagal]), 1.0, None)
    assert h.perilaku_benar and not h.tool_benar_percobaan_pertama and h.galat_tool == 1


def test_info_needs_legal_basis_search():
    k = _kasus("inf-01")
    search = [_panggil("find_legal_basis", topic="biaya_jabatan")]
    benar = score_case(k, AgentTurn(answer="Biaya jabatan 5%, paling banyak Rp6.000.000 setahun.", trace=search),
                       1.0, None)
    tanpa_fakta = score_case(k, AgentTurn(answer="Ada di PMK 168/2023.", trace=search), 1.0, None)
    salah = score_case(k, AgentTurn(answer="Pasal 21 ayat (3)"), 1.0, None)
    assert benar.perilaku_benar and not tanpa_fakta.perilaku_benar and not salah.perilaku_benar


def test_hallucinated_tool_recorded():
    k = _kasus("pt-ter-02")
    p = AgentTurn(trace=[Jejak("hitung_pph21_karyawan", {}, {"berhasil": False})])
    h = score_case(k, p, 1.0, reference_result(k))
    assert h.tool_halusinasi == ["hitung_pph21_karyawan"] and not h.perilaku_benar


class AgentPalsu:
    def __init__(self, respons):
        self._respons = respons

    def ask(self, pertanyaan):
        r = self._respons(pertanyaan)
        if isinstance(r, Exception):
            raise r
        return r


def test_single_clarification_with_default_scored_separately():
    from taxagent.evaluation.scorer import CLARIFICATION_REPLY

    k = _kasus("bp-02")

    def respons(pertanyaan):
        if pertanyaan == CLARIFICATION_REPLY:
            return AgentTurn(trace=[_panggil(k["tool"], **k["argumen"])], answer="Rp175.000")
        return AgentTurn(answer="Apakah penerima punya NPWP? (default: ya)")

    [h] = run_cases([k], lambda: AgentPalsu(respons), retry_delay=0)
    assert h.klarifikasi and h.perilaku_benar and not h.perilaku_benar_satu_giliran
    assert h.token_masuk == 0 and h.sitasi_belum_terverifikasi == []
    r = summarize([h])
    assert r["akurasi_keseluruhan"] == 1.0 and r["akurasi_satu_giliran"] == 0.0
    assert r["klarifikasi_tidak_perlu"] == 1


def test_clarified_case_keeps_tokens_and_checker_fields_of_the_final_answer():
    from taxagent.agent.runner import AgentTurn
    from taxagent.evaluation.scorer import CLARIFICATION_REPLY

    k = _kasus("bp-02")

    def respons(pertanyaan):
        if pertanyaan == CLARIFICATION_REPLY:
            return AgentTurn(trace=[_panggil(k["tool"], **k["argumen"])], answer="Rp175.000", tokens_in=900,
                             tokens_out=90, citation_unverified=["PMK 1 Tahun 2099 disebut tetapi tidak berasal dari "
                                                                 "hasil tool di percakapan ini"],
                             citation_corrections=["koreksi kedua"], status_stamped=["PMK 252 Tahun 2008"])
        return AgentTurn(answer="Apakah penerima punya NPWP?", tokens_in=400, tokens_out=40,
                         citation_corrections=["koreksi pertama"])

    [h] = run_cases([k], lambda: AgentPalsu(respons), retry_delay=0)
    assert h.klarifikasi and (h.token_masuk, h.token_keluar) == (900, 90)
    assert h.sitasi_belum_terverifikasi and h.status_distempel == ["PMK 252 Tahun 2008"]
    assert h.sitasi_dikoreksi == ["koreksi pertama", "koreksi kedua"]
    import datetime as dt
    import json

    from taxagent.agent.runner import ToolCall
    from taxagent.evaluation.scorer import RESULT_CHARS, _trace_record
    assert h.jejak[0]["tool"] == k["tool"] and h.jejak[0]["hasil"]["berhasil"] is True
    rec = _trace_record([ToolCall(name="x", arguments={"tanggal": dt.date(2024, 1, 1)},
                                  result={"tgl": dt.date(2024, 1, 1), "teks": "a" * (RESULT_CHARS + 10)})])
    json.dumps(rec)
    assert rec[0]["argumen"] == {"tanggal": "2024-01-01"} and rec[0]["hasil"]["terpotong"] is True
    r = summarize([h])
    assert r["jawaban_sitasi_bermasalah"] == 1 and r["pemeriksa_sitasi"]["jawaban_distempel_status"] == 1


def test_run_and_summary_including_api_errors():
    ks = [_kasus("pt-ter-02"), _kasus("tb-01")]

    def respons(pertanyaan):
        if "10 juta" in pertanyaan and "TK/0" in pertanyaan:
            return AgentTurn(trace=[_panggil(ks[0]["tool"], **ks[0]["argumen"])])
        return RuntimeError("429 rate limit")

    hasil = run_cases(ks, lambda: AgentPalsu(respons), retries=2, retry_delay=0)
    r = summarize(hasil)
    assert hasil[0].perilaku_benar
    assert hasil[1].error and not hasil[1].perilaku_benar
    assert r["n_error_api"] == 1 and r["akurasi_keseluruhan"] == 0.5
    assert r["hitung"]["akurasi_angka_akhir"] == 1.0


def test_number_faithfulness_flags_amounts_without_source():
    from taxagent.agent.runner import ToolCall
    from taxagent.evaluation.scorer import number_faithfulness

    trace = [ToolCall(name="calculate_pph21_monthly", arguments={"bruto": 10000000},
                      result={"berhasil": True, "pph_terutang": 225000, "rincian": {"ter": "2,25%"}})]
    case = {"pertanyaan": "gaji Rp10.000.000 sebulan"}
    ok = number_faithfulness("Dengan bruto Rp10.000.000, PPh 21 Maret Rp225.000.", trace, case)
    assert ok == ([], True)
    made_up = number_faithfulness("PPh 21 Rp225.000, setahun sekitar Rp2.700.000.", trace, case)
    assert made_up == ([2700000], True)
    missing = number_faithfulness("PPh 21 Anda Rp250.000.", trace, case)
    assert missing == ([250000], False)
    assert number_faithfulness("Tidak ada angka.", [], case) == ([], None)


def test_api_error_cases_are_retried_in_later_rounds_and_counted_apart():
    ks = [_kasus("pt-ter-02")]
    calls = {"n": 0}

    def respons(pertanyaan):
        calls["n"] += 1
        if calls["n"] <= 3:
            return RuntimeError("429 rate limit")
        return AgentTurn(trace=[_panggil(ks[0]["tool"], **ks[0]["argumen"])])

    seen = []
    hasil = run_cases(ks, lambda: AgentPalsu(respons), retries=2, retry_delay=0, retry_rounds=2, round_delay=0,
                      on_done=seen.append)
    r = summarize(hasil)
    assert hasil[0].perilaku_benar and not hasil[0].error and len(hasil[0].galat_api) == 3
    assert r["n_error_api"] == 0 and r["n_galat_api_diulang"] == 3 and r["kasus_diulang"] == ["pt-ter-02"]
    assert [h.error is None for h in seen] == [False, True]


def test_agent_tokens_are_counted_per_case() -> None:
    from types import SimpleNamespace

    from taxagent.agent.runner import TaxAgent

    class Fake:
        def invoke(self, messages, **kw):
            return SimpleNamespace(content="ok", tool_calls=[], usage_metadata={"input_tokens": 10, "output_tokens": 3})

    agent = TaxAgent.__new__(TaxAgent)
    agent.llm = Fake()
    agent._invoke([])
    agent._invoke([])
    assert (agent.tokens_in, agent.tokens_out) == (20, 6)
