from __future__ import annotations

import pytest

pytest.importorskip("langchain_core", reason="lapis agent butuh langchain-core")

from langchain_core.messages import AIMessage  # noqa: E402

from taxagent.agent import TaxAgent  # noqa: E402
from taxagent.agent.runner import names_other_tax  # noqa: E402


class LLMTiruan:
    def __init__(self, balasan: list[AIMessage]):
        self._balasan = list(balasan)

    def invoke(self, messages):
        return self._balasan.pop(0) if self._balasan else AIMessage(content="(kehabisan balasan tiruan)")


def _panggil(nama, args, i):
    return AIMessage(content="", tool_calls=[{"name": nama, "args": args, "id": f"call-{i}"}])


@pytest.mark.parametrize("pesan", [
    "Berapa PPh badan untuk perusahaan dengan laba kena pajak 1 miliar di 2025?",
    "Hitung PPN atas penjualan barang senilai 100 juta.",
    "Berapa PPh Pasal 23 atas jasa konsultan 50 juta?",
    "Tarif PPh 4 ayat (2) untuk sewa bangunan berapa?",
    "PPh 4(2) UMKM omzet 300 juta",
    "Bea meterai untuk kontrak 10 juta berapa?",
    "Pajak Pertambahan Nilai atas jasa digital",
])
def test_other_tax_types_detected(pesan):
    assert names_other_tax(pesan)


@pytest.mark.parametrize("pesan", [
    "Karyawan TK/0 gaji 10 juta Maret 2025, berapa PPh 21?",
    "Gaji 20 juta K/1, PPh 21 dan PPh 23 atas jasanya berapa?",
    "Berapa PPh Pasal 26 atas honor 100 juta untuk WP luar negeri?",
    "PPh 210 itu apa?",
    "Pegawai PT ABC gaji 15 juta, status kawin anak 2",
])
def test_pph21_and_plain_questions_not_flagged(pesan):
    assert not names_other_tax(pesan)


def test_corporate_tax_question_cannot_be_calculated_with_pph21_tool():
    llm = LLMTiruan([
        _panggil("calculate_pph21_direct_pasal_17", {"penghasilan_kena_pajak": 1_000_000_000, "tahun_pajak": 2025}, 1),
        _panggil("find_legal_basis", {"topic": "ptkp"}, 2),
        AIMessage(content="PPh badan di luar cakupan kalkulator ini."),
    ])
    hasil = TaxAgent(llm=llm).ask("Berapa PPh badan untuk perusahaan dengan laba kena pajak 1 miliar di 2025?")
    assert hasil.trace[0].result["berhasil"] is False
    assert "PPh 21" in hasil.trace[0].result["galat"]
    assert hasil.trace[1].result["berhasil"] is True


def test_scope_guard_follows_the_latest_message():
    llm = LLMTiruan([
        AIMessage(content="PPN di luar cakupan."),
        _panggil("calculate_pph21_permanent_monthly",
                 {"gaji_pokok": 10_000_000, "status_ptkp": "TK/0", "kutipan_status_ptkp": "TK/0",
                  "masa_pajak": 3, "tahun_pajak": 2025}, 1),
        AIMessage(content="ok"),
    ])
    agent = TaxAgent(llm=llm)
    agent.ask("Hitung PPN atas penjualan 100 juta.")
    hasil = agent.ask("Kalau begitu PPh 21 karyawan TK/0 gaji 10 juta Maret 2025?")
    assert hasil.trace[0].result["berhasil"] is True
