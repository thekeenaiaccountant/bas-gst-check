"""ABN checksum. A real ABN passes the ABR modulus check. Example data must not."""

from __future__ import annotations

import re

WEIGHTS = (10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19)


def digits_only(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def abn_is_valid(value: str) -> bool:
    """Return True when the value is an 11-digit ABN with a valid checksum."""
    digits = digits_only(value)
    if len(digits) != 11:
        return False
    numbers = [int(character) for character in digits]
    numbers[0] -= 1
    if numbers[0] < 0:
        return False
    total = sum(number * weight for number, weight in zip(numbers, WEIGHTS))
    return total % 89 == 0
