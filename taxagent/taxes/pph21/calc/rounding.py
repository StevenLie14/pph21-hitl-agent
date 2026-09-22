from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

ONE = Decimal("1")


def money(value) -> Decimal:
    if isinstance(value, Decimal):
        d = value
    elif isinstance(value, float):
        d = Decimal(str(value))
    else:
        d = Decimal(value)

    whole = d.to_integral_value(rounding=ROUND_DOWN)
    return whole if d == whole else d


def round_down(value, multiple: int = 1) -> Decimal:
    value = money(value)
    if multiple <= 1:
        return value.quantize(ONE, rounding=ROUND_DOWN)
    k = Decimal(multiple)
    return (value / k).quantize(ONE, rounding=ROUND_DOWN) * k


def round_rupiah(value) -> Decimal:
    return round_down(value, 1)


def percent(value, rate) -> Decimal:
    return money(value) * money(rate) / Decimal(100)


def format_rupiah(value) -> str:
    value = money(value)
    negative = value < 0
    whole = int(abs(value).quantize(ONE, rounding=ROUND_DOWN))
    text = f"{whole:,}".replace(",", ".")
    return ("-Rp" if negative else "Rp") + text
