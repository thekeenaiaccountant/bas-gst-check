"""Decimal money helpers. Amounts stay in cents, never binary floats."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")
GST_DIVISOR = Decimal(11)


def parse_money(value: object) -> Decimal:
    """Parse a money cell. Strings are preferred. Floats are accepted at two decimals."""
    if isinstance(value, Decimal):
        return cents(value)
    if isinstance(value, bool):
        raise ValueError("a yes/no value is not an amount")
    if isinstance(value, int):
        return cents(Decimal(value))
    if isinstance(value, float):
        return cents(Decimal(str(value)))
    if isinstance(value, str):
        cleaned = value.strip().replace("$", "").replace(",", "").replace(" ", "")
        if not cleaned:
            raise ValueError("the amount is blank")
        if cleaned.startswith("(") and cleaned.endswith(")"):
            cleaned = "-" + cleaned[1:-1]
        return cents(Decimal(cleaned))
    raise ValueError("the amount is not a number")


def cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def expected_gst(inclusive: Decimal) -> Decimal:
    """GST is one-eleventh of the GST-inclusive amount, rounded to the nearest cent."""
    return cents(inclusive / GST_DIVISOR)


def money_text(value: Decimal) -> str:
    """Format dollars for the report, with a leading minus if needed."""
    quantized = cents(value)
    sign = "-" if quantized < 0 else ""
    number = f"{abs(quantized):,.2f}"
    return f"{sign}${number}"
