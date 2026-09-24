from __future__ import annotations

import json

import pytest

pytest.importorskip("langchain_core", reason="lapis agent butuh langchain-core")

from langchain_core.messages import AIMessage  # noqa: E402

from taxagent.agent import TaxAgent  # noqa: E402
from taxagent.taxes.pph21.calc.rates import default_year, load_rates  # noqa: E402


class LLMTiruan:
    def __init__(self, balasan: list[AIMessage]):
        self._balasan = list(balasan)
        self.panggilan_masuk: list[list] = []

    def invoke(self, messages):
        self.panggilan_masuk.append(list(messages))
        if not self._balasan:
            return AIMessage(content="(kehabisan balasan tiruan)")
        return self._balasan.pop(0)


def _agent(balasan: list[AIMessage]) -> tuple[TaxAgent, LLMTiruan]:
    llm = LLMTiruan(balasan)
    return TaxAgent(llm=llm), llm


def test_tool_called_with_exact_arguments():
    argumen = {
        "gaji_pokok": 15_000_000,
        "tunjangan_tidak_tetap": 1_000_000,
        "status_ptkp": "K/1",
        "kutipan_status_ptkp": "K/1",
        "masa_pajak": 3,
        "tahun_pajak": 2025,
    }
    agent, _ = _agent(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "calculate_pph21_permanent_monthly",
                        "args": argumen,
                        "id": "call-1",
                    }
                ],
            ),
            AIMessage(content="PPh 21 masa Maret 2025 adalah Rp960.000."),
        ]
    )
    hasil = agent.ask("gaji 15 juta tunjangan 1 juta, K/1, Maret 2025")

    assert hasil.called_tool_names() == ["calculate_pph21_permanent_monthly"]
    assert hasil.trace[0].arguments == argumen
    assert hasil.trace[0].result["pph_terutang"] == "960000"
    assert "960.000" in hasil.answer


def test_two_tool_chain_lookup_then_calculate():
    agent, _ = _agent(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "lookup_ptkp",
                        "args": {"kawin": True, "jumlah_tanggungan": 1, "tahun_pajak": 2025,
                                 "kutipan_status_ptkp": "menikah anak 1"},
                        "id": "c1",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "calculate_pph21_permanent_monthly",
                        "args": {
                            "gaji_pokok": 16_000_000,
                            "status_ptkp": "K/1",
                            "kutipan_status_ptkp": "menikah anak 1",
                            "masa_pajak": 3,
                            "tahun_pajak": 2025,
                        },
                        "id": "c2",
                    }
                ],
            ),
            AIMessage(content="selesai"),
        ]
    )
    hasil = agent.ask("menikah anak 1, gaji 16 juta, Maret")

    assert hasil.called_tool_names() == ["lookup_ptkp", "calculate_pph21_permanent_monthly"]
    assert hasil.trace[0].result["status_ptkp"] == "K/1"
    assert hasil.trace[0].result["kategori_ter"] == "B"
    assert hasil.rounds == 3


def test_tool_error_returned_to_model_as_data():
    agent, llm = _agent(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "calculate_pph21_permanent_monthly",
                        "args": {"gaji_pokok": 10_000_000, "status_ptkp": "NGAWUR", "masa_pajak": 1},
                        "id": "c1",
                    }
                ],
            ),
            AIMessage(content="Status PTKP-nya apa ya?"),
        ]
    )
    hasil = agent.ask("hitung dong")

    assert hasil.trace[0].result["berhasil"] is False
    pesan_tool = llm.panggilan_masuk[-1][-1]
    isi = json.loads(pesan_tool.content)
    assert isi["berhasil"] is False
    assert "saran" in isi


def test_unknown_tool_does_not_crash():
    agent, _ = _agent(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "hitung_pajak_ajaib", "args": {}, "id": "c1"}],
            ),
            AIMessage(content="maaf"),
        ]
    )
    hasil = agent.ask("apa saja")
    assert hasil.trace[0].result["berhasil"] is False


def test_answer_without_tool_finishes_immediately():
    agent, _ = _agent([AIMessage(content="PPh 21 adalah pajak atas penghasilan sehubungan pekerjaan.")])
    hasil = agent.ask("PPh 21 itu apa?")
    assert hasil.trace == []
    assert hasil.rounds == 1


def test_loop_stops_at_turn_limit():
    from taxagent.agent.runner import MAX_TURNS

    balasan = [
        AIMessage(
            content="",
            tool_calls=[{"name": "lookup_pasal_17_rates", "args": {"tahun_pajak": 2025}, "id": f"c{i}"}],
        )
        for i in range(MAX_TURNS + 5)
    ]
    agent, _ = _agent(balasan)
    hasil = agent.ask("terus saja")
    assert hasil.rounds == MAX_TURNS
    assert "Berhenti setelah" in hasil.answer


def test_turn_limit_answered_from_existing_tool_results():
    from taxagent.agent.runner import MAX_TURNS, TURN_LIMIT_NOTICE

    balasan = [
        AIMessage(content="", tool_calls=[{"name": "lookup_pasal_17_rates", "args": {"tahun_pajak": 2025},
                                           "id": f"c{i}"}])
        for i in range(MAX_TURNS)
    ] + [AIMessage(content="Tarif Pasal 17 lapisan pertama 5%.")]
    agent, _ = _agent(balasan)
    hasil = agent.ask("terus saja")
    assert hasil.rounds == MAX_TURNS + 1 and hasil.answer == "Tarif Pasal 17 lapisan pertama 5%."
    assert len(hasil.trace) == MAX_TURNS
    assert TURN_LIMIT_NOTICE not in [getattr(m, "content", "") for m in agent.riwayat]


def test_provenance_warning_reaches_model(monkeypatch):
    monkeypatch.setattr(load_rates(default_year()), "terverifikasi", False)
    agent, llm = _agent(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "calculate_pph21_permanent_monthly",
                        "args": {"gaji_pokok": 10_000_000, "status_ptkp": "TK/0", "masa_pajak": 1,
                                 "kutipan_status_ptkp": "TK/0"},
                        "id": "c1",
                    }
                ],
            ),
            AIMessage(content="selesai"),
        ]
    )
    agent.ask("hitung, TK/0")
    isi = json.loads(llm.panggilan_masuk[-1][-1].content)
    assert isi["peringatan"], "peringatan hilang sebelum sampai ke model"


def _panggil(nama, args, i):
    return AIMessage(content="", tool_calls=[{"name": nama, "args": args, "id": f"call-{i}"}])


def test_ki_status_cannot_be_calculated_even_if_model_switches_to_k1():
    agent, _ = _agent([
        _panggil("lookup_ptkp", {"kawin": True, "jumlah_tanggungan": 1}, 1),
        _panggil("calculate_pph21_permanent_monthly",
                 {"gaji_pokok": 15_000_000, "status_ptkp": "K/1", "masa_pajak": 3, "tahun_pajak": 2025}, 2),
        AIMessage(content="Status K/I/1 tidak didukung."),
    ])
    hasil = agent.ask("Suami istri penghasilan digabung (status K/I/1). Gaji istri 15 juta Maret 2025. PPh 21?")
    assert [j.result["berhasil"] for j in hasil.trace] == [False, False]
    assert "K/I" in hasil.trace[1].result["galat"] and "Jangan mengganti" in hasil.trace[1].result["saran"]


def test_ki_guard_does_not_disturb_info_tools_and_other_messages():
    agent, _ = _agent([_panggil("find_legal_basis", {"topic": "ptkp"}, 1), AIMessage(content="ok")])
    hasil = agent.ask("Apa dasar hukum PTKP? Saya dengar ada status K/I/0.")
    assert hasil.trace[0].result["berhasil"] is True
    agent2, _ = _agent([
        _panggil("calculate_pph21_permanent_monthly",
                 {"gaji_pokok": 10_000_000, "status_ptkp": "K/1", "kutipan_status_ptkp": "Karyawan K/1",
                  "masa_pajak": 3, "tahun_pajak": 2025}, 1),
        AIMessage(content="ok"),
    ])
    assert agent2.ask("Karyawan K/1 gaji 10 juta Maret 2025, kini di KIT/1 cabang").trace[0].result["berhasil"] is True


def test_ptkp_status_must_not_be_guessed():
    arg = {"gaji_pokok": 20_000_000, "status_ptkp": "TK/0", "masa_pajak": 5, "tahun_pajak": 2025}
    agent, _ = _agent([_panggil("calculate_pph21_permanent_monthly", arg, 1), AIMessage(content="Status PTKP?")])
    h = agent.ask("Karyawan tetap gaji 20 juta per bulan, bulan Mei 2025. Hitung PPh 21-nya.")
    assert h.trace[0].result["berhasil"] is False and "tidak boleh ditebak" in h.trace[0].result["galat"]
    agent.llm._balasan = [
        _panggil("calculate_pph21_permanent_monthly", {**arg, "kutipan_status_ptkp": "belum menikah, tanpa tanggungan"}, 2),
        AIMessage(content="Rp1.800.000"),
    ]
    assert agent.ask("Belum menikah,  tanpa tanggungan.").trace[0].result["berhasil"] is True


def test_made_up_quote_rejected():
    arg = {"gaji_pokok": 20_000_000, "status_ptkp": "TK/0", "kutipan_status_ptkp": "saya lajang",
           "masa_pajak": 5, "tahun_pajak": 2025}
    agent, _ = _agent([_panggil("calculate_pph21_permanent_monthly", arg, 1), AIMessage(content="?")])
    assert agent.ask("Karyawan tetap gaji 20 juta, Mei 2025.").trace[0].result["berhasil"] is False


def test_verbatim_quote_without_status_rejected():
    arg = {"gaji_pokok": 20_000_000, "status_ptkp": "TK/0", "kutipan_status_ptkp": "Karyawan tetap gaji 20 juta",
           "masa_pajak": 5, "tahun_pajak": 2025}
    agent, _ = _agent([_panggil("calculate_pph21_permanent_monthly", arg, 1), AIMessage(content="?")])
    h = agent.ask("Karyawan tetap gaji 20 juta per bulan, bulan Mei 2025. Hitung PPh 21-nya.")
    assert h.trace[0].result["berhasil"] is False and "tidak menyebut status" in h.trace[0].result["galat"]


def test_status_markers():
    from taxagent.agent.runner import states_status
    for ok in ("K/1", "tk/0", "TK0", "menikah anak 1", "belum kawin", "lajang", "punya 2 tanggungan", "istri dan 3 anak",
               "masih sendiri, belum berkeluarga", "duda"):
        assert states_status(ok), ok
    for bad in ("Karyawan tetap", "gaji 20 juta per bulan", "bulan Mei 2025", "punya NPWP", "kantor K3"):
        assert not states_status(bad), bad


def test_free_phrase_quote_accepted_without_word_list():
    arg = {"gaji_pokok": 20_000_000, "status_ptkp": "TK/0", "kutipan_status_ptkp": "masih sendiri, belum berkeluarga",
           "masa_pajak": 5, "tahun_pajak": 2025}
    agent, _ = _agent([_panggil("calculate_pph21_permanent_monthly", arg, 1), AIMessage(content="ok")])
    h = agent.ask("Saya masih sendiri, belum berkeluarga. Gaji 20 juta, Mei 2025.")
    assert h.trace[0].result["berhasil"] is True


def test_ptkp_code_in_any_spelling():
    from taxagent.agent.runner import ptkp_codes
    for quote, code in [("status k2", "K/2"), ("k1", "K/1"), ("K/2", "K/2"), ("k 2", "K/2"), ("K-1", "K/1"),
                        ("TK / 0", "TK/0"), ("tk.0", "TK/0"), ("TK0", "TK/0"), ("ptkp K3", "K/3")]:
        assert ptkp_codes(quote) == {code}, quote
    for quote in ("kantor K3", "iuran k3 dibayar", "pk2", "k/i/1", "nikah anak 3", "gaji 20 juta"):
        assert ptkp_codes(quote) == set(), quote


def test_quoted_code_must_match_the_chosen_status():
    arg = {"gaji_pokok": 6_500_000, "status_ptkp": "K/1", "kutipan_status_ptkp": "status k2",
           "masa_pajak": 7, "tahun_pajak": 2024}
    agent, _ = _agent([_panggil("calculate_pph21_permanent_monthly", arg, 1), AIMessage(content="?")])
    h = agent.ask("gaji 6,5jt juli 2024. status k2 karyawan tetap")
    assert h.trace[0].result["berhasil"] is False and "menyebut kode K/2" in h.trace[0].result["galat"]
    agent2, _ = _agent([_panggil("calculate_pph21_permanent_monthly", {**arg, "status_ptkp": "K/2"}, 1),
                        AIMessage(content="ok")])
    assert agent2.ask("gaji 6,5jt juli 2024. status k2 karyawan tetap").trace[0].result["berhasil"] is True


def test_tool_without_ptkp_status_not_guarded():
    agent, _ = _agent([_panggil("calculate_pph21_non_employee", {"penghasilan_bruto": 7_000_000, "tahun_pajak": 2024}, 1),
                       AIMessage(content="ok")])
    assert agent.ask("Konsultan menerima 7 juta November 2024").trace[0].result["berhasil"] is True


def test_unsourced_amount_gets_one_correction_then_a_note():
    agent, llm = _agent([AIMessage(content="PPN-nya Rp11.000.000."), AIMessage(content="PPN-nya Rp11.000.000.")])
    h = agent.ask("Saya jual jasa 100 juta, berapa PPN-nya?")
    assert h.number_corrections == [11_000_000] and h.numbers_unsourced == [11_000_000]
    assert "Pemeriksa angka otomatis" in llm.panggilan_masuk[1][-1].content
    assert h.answer.startswith("PPN-nya Rp11.000.000.") and "Rp11.000.000" in h.answer.split("Catatan pemeriksa angka")[1]


def test_corrected_answer_has_no_note():
    agent, _ = _agent([AIMessage(content="PPN-nya Rp11.000.000."),
                       AIMessage(content="Kalkulator ini hanya menghitung PPh 21; PPN tidak saya hitung.")])
    h = agent.ask("Saya jual jasa 100 juta, berapa PPN-nya?")
    assert h.number_corrections == [11_000_000] and h.numbers_unsourced == [] and "Catatan" not in h.answer


def test_spoken_amount_in_answer_is_checked():
    agent, _ = _agent([AIMessage(content="PPh badan **Rp220 juta**."), AIMessage(content="PPh badan Rp220 juta.")])
    h = agent.ask("Berapa PPh badan untuk laba kena pajak 1 miliar di 2025?")
    assert h.number_corrections == [220_000_000] and h.numbers_unsourced == [220_000_000]


def test_amount_forms():
    from taxagent.agent.numbers import numbers_in, unsourced

    assert numbers_in("Rp220 juta, Rp 1 miliar, 2,5 jt, Rp1.500 juta") == {220_000_000, 10**9, 2_500_000, 1_500_000_000}
    assert numbers_in("Rp54.000.000, lalu Rp 5.000.000,00 per bulan.") == {54_000_000, 5_000_000}
    assert unsourced("PTKP Rp54 juta, tarif 5%, PPh Rp1.800.000.", {54_000_000}) == [1_800_000]


def test_amounts_from_user_or_tools_are_sourced():
    agent, llm = _agent([AIMessage(content="Gaji Rp20.000.000 sebulan; status PTKP-nya apa?")])
    h = agent.ask("Karyawan tetap gaji 20 juta per bulan, Mei 2025.")
    assert h.number_corrections == [] and len(llm.panggilan_masuk) == 1
    arg = {"gaji_pokok": 20_000_000, "status_ptkp": "TK/0", "kutipan_status_ptkp": "lajang",
           "masa_pajak": 5, "tahun_pajak": 2025}
    agent, _ = _agent([_panggil("calculate_pph21_permanent_monthly", arg, 1), AIMessage(content="PPh Rp1.800.000.")])
    assert agent.ask("Saya lajang, gaji 20 juta, Mei 2025.").number_corrections == []
