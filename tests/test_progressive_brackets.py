from decimal import Decimal

import pytest

from taxagent.taxes.pph21.calc.rates import Bracket, calc_progressive


def test_empty_brackets_raise_instead_of_zero():
    with pytest.raises(ValueError, match="kosong"):
        calc_progressive(120_000_000, [])


def test_brackets_without_top_bracket_raise_when_exceeded():
    with pytest.raises(ValueError, match="tidak lengkap"):
        calc_progressive(120_000_000, [Bracket(50_000_000, 0), Bracket(100_000_000, 5)])


def test_brackets_without_top_bracket_are_fine_within_limit():
    total, _ = calc_progressive(80_000_000, [Bracket(50_000_000, 0), Bracket(100_000_000, 5)])
    assert total == Decimal(1_500_000)


def test_pesangon_brackets_pp_68_2009():
    brackets = [Bracket(50_000_000, 0), Bracket(100_000_000, 5), Bracket(500_000_000, 15), Bracket(None, 25)]
    total, _ = calc_progressive(120_000_000, brackets)
    assert total == Decimal(5_500_000)
