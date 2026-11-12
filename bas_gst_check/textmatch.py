"""Phrase matching used by the GST checks."""

from __future__ import annotations

import re


def normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def contains_phrase(text: str, phrase: str) -> bool:
    haystack = normalise(text)
    needle = normalise(phrase)
    if not needle:
        return False
    if " " in needle:
        return needle in haystack
    return re.search(rf"\b{re.escape(needle)}\b", haystack) is not None


def any_phrase(text: str, phrases: list[str]) -> str | None:
    for phrase in phrases:
        if contains_phrase(text, phrase):
            return phrase
    return None
