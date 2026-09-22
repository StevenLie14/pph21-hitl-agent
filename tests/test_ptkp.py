from decimal import Decimal

import pytest

from taxagent.taxes.pph21.calc import PTKPStatus, annual_ptkp, parse_ptkp_status, ptkp_code
from taxagent.taxes.pph21.calc.ptkp import InvalidPTKPStatus

TAHUN = 2025


@pytest.mark.parametrize(
    "kawin,tanggungan,harapan",
    [
        (False, 0, "TK/0"),
        (False, 1, "TK/1"),
        (False, 3, "TK/3"),
        (True, 0, "K/0"),
        (True, 1, "K/1"),
        (True, 3, "K/3"),
    ],
)
def test_ptkp_code(kawin, tanggungan, harapan):
    status, peringatan = ptkp_code(kawin, tanggungan, TAHUN)
    assert status.value == harapan
    assert peringatan == []


def test_dependants_over_limit_capped_and_reported():
    status, peringatan = ptkp_code(True, 5, TAHUN)
    assert status is PTKPStatus.K3
    assert peringatan, "kelebihan tanggungan harus dilaporkan, bukan didiamkan"
    assert "melebihi batas" in peringatan[0]


def test_negative_dependants_rejected():
    with pytest.raises(InvalidPTKPStatus):
        ptkp_code(False, -1, TAHUN)


@pytest.mark.parametrize(
    "status,harapan",
    [
        ("TK/0", 54_000_000),
        ("TK/1", 58_500_000),
        ("TK/2", 63_000_000),
        ("TK/3", 67_500_000),
        ("K/0", 58_500_000),
        ("K/1", 63_000_000),
        ("K/2", 67_500_000),
        ("K/3", 72_000_000),
    ],
)
def test_ptkp_amount(status, harapan):
    assert annual_ptkp(parse_ptkp_status(status), TAHUN) == Decimal(harapan)


@pytest.mark.parametrize("teks", ["K/1", "k/1", "k1", "K 1", "K-1", " K/1 "])
def test_parse_status_tolerant(teks):
    assert parse_ptkp_status(teks) is PTKPStatus.K1


def test_parse_unrecognised_status():
    with pytest.raises(InvalidPTKPStatus) as exc:
        parse_ptkp_status("MENIKAH")
    assert "TK/0" in str(exc.value), "pesan galat harus menyebut pilihan yang valid"
