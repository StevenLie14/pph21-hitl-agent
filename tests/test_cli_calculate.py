from __future__ import annotations

import pytest

from taxagent.cli import build_parser, main


def jalankan(capsys, *argv: str) -> tuple[int, str, str]:
    kode = main(list(argv))
    keluar = capsys.readouterr()
    return kode, keluar.out, keluar.err


def test_rates_show_ptkp_and_pasal_17_brackets(capsys):
    kode, out, _ = jalankan(capsys, "rates", "--year", "2024")
    assert kode == 0
    assert "TK/0" in out and "54.000.000" in out and "kategori A: " in out


def test_unavailable_year_rates_exit_1(capsys):
    kode, _, err = jalankan(capsys, "rates", "--year", "1999")
    assert kode == 1 and "1999" in err


def test_calculate_monthly_ter(capsys):
    kode, out, _ = jalankan(capsys, "calculate", "monthly", "--gaji-pokok", "10000000", "--status", "TK/0",
                            "--masa", "1", "--year", "2024")
    assert kode == 0 and "PPh 21 TERUTANG: Rp200.000" in out


def test_calculate_annual_pensioner_uses_biaya_pensiun(capsys):
    kode, out, _ = jalankan(capsys, "calculate", "pensioner-annual", "--uang-pensiun", "60000000", "--status", "TK/0",
                            "--year", "2024")
    assert kode == 0 and "Biaya pensiun" in out and "Biaya jabatan" not in out


@pytest.mark.parametrize("argv", [
    ["calculate", "non-permanent", "--upah", "600000"],
    ["calculate", "non-employee", "--bruto", "10000000"],
    ["calculate", "commissioner", "--bruto", "20000000", "--status", "TK/0"],
    ["calculate", "final", "--jenis", "pesangon", "--bruto", "600000000"],
    ["calculate", "article17-direct", "--jenis", "mantan_pegawai", "--bruto", "100000000", "--tanpa-npwp"],
    ["calculate", "pph26", "--bruto", "10000000", "--tarif-p3b", "10", "--skd"],
    ["ptkp", "--kawin", "--tanggungan", "2"],
])
def test_every_subcommand_succeeds(capsys, argv):
    kode, out, err = jalankan(capsys, *argv, "--year", "2024")
    assert kode == 0, err
    assert out.strip()


def test_wrong_ptkp_status_rejected_by_tool(capsys):
    kode, _, err = jalankan(capsys, "calculate", "monthly", "--gaji-pokok", "1", "--status", "XX/9", "--masa", "1")
    assert kode == 1 and "GAGAL" in err


def test_tool_invalid_json(capsys):
    kode, _, err = jalankan(capsys, "tool", "lookup_ptkp", "--json", "{bad")
    assert kode == 1 and "JSON tidak valid" in err


def test_lookup_tool_prints_json(capsys):
    kode, out, _ = jalankan(capsys, "tool", "lookup_ptkp", "--json", '{"kawin": true, "jumlah_tanggungan": 1}')
    assert kode == 0 and '"status_ptkp": "K/1"' in out


def test_all_subcommands_registered():
    sub = next(a for a in build_parser()._actions if a.dest == "command")
    assert set(sub.choices) == {
        "rates", "verify", "ptkp", "calculate", "tool", "ask", "chat", "evaluate", "agent-backtest", "monitor",
        "graph-ingest", "pajak-sweep", "monitor-review", "agent-requests", "monitor-evaluate", "monitor-evaluate-llm",
        "monitor-impact", "draft-rates", "review-draft", "draft-evaluate", "draft-backtest"}


def test_tool_rejects_unknown_arguments(capsys):
    kode, _, err = jalankan(capsys, "tool", "calculate_pph21_non_employee", "--json",
                            '{"penghasilan_bruto": 1000000, "penghasilan_brutto": 5}')
    assert kode == 1 and "argumen tidak dikenal" in err and "penghasilan_brutto" in err
