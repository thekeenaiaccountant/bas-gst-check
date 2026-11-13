"""Suggested GST codes and possible personal spend. Always a hint, never a ruling."""

from __future__ import annotations

import json
from pathlib import Path

from bas_gst_check.models import Flag, Transaction
from bas_gst_check.rules import Rules
from bas_gst_check.sources import CANNOT_CLAIM, SOURCE_TITLES
from bas_gst_check.textmatch import any_phrase


def load_ai_suggestions(path: Path | None) -> dict:
    if path is None or not path.is_file():
        return {"codes": [], "personal": []}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"codes": [], "personal": []}
    if not isinstance(raw, dict):
        return {"codes": [], "personal": []}
    codes = raw.get("codes") if isinstance(raw.get("codes"), list) else []
    personal = raw.get("personal") if isinstance(raw.get("personal"), list) else []
    return {"codes": codes, "personal": personal}


def suggest_flags(
    transactions: list[Transaction],
    rules: Rules,
    ai: dict | None = None,
) -> list[Flag]:
    extras = ai or {"codes": [], "personal": []}
    flags: list[Flag] = []
    for transaction in transactions:
        text = f"{transaction.description} {transaction.account}"
        if _already_an_error_hint(text, rules):
            continue
        match = _rule_suggestion(text, transaction, rules)
        if match is None:
            match = _ai_code(transaction, extras["codes"])
        if match is None:
            continue
        suggest, why, detail = match
        if _same_code(transaction.tax_code_label, suggest):
            continue
        flags.append(Flag(
            code="suggested_code",
            title="Suggested GST code",
            severity="review",
            why=why,
            fix=_suggestion_line(why, suggest),
            source_url=CANNOT_CLAIM,
            source_title=SOURCE_TITLES[CANNOT_CLAIM],
            transaction=transaction,
            detail_key=detail,
        ))
    for transaction in transactions:
        phrase = any_phrase(f"{transaction.description} {transaction.account}", list(rules.personal_phrases))
        ai_hit = phrase is None and _ai_personal(transaction, extras["personal"])
        if phrase is None and not ai_hit:
            continue
        matched = phrase or "the note from this check"
        flags.append(Flag(
            code="personal_spend",
            title="May be personal",
            severity="review",
            why=(
                f"May be personal, check. The wording '{matched}' can be household or private. "
                "It is only a hint from the words."
            ),
            fix="May be personal, check. Leave it in the business if it is a real business cost.",
            source_url=CANNOT_CLAIM,
            source_title=SOURCE_TITLES[CANNOT_CLAIM],
            transaction=transaction,
            detail_key=matched,
        ))
    return flags


def _suggestion_line(why: str, suggest: str) -> str:
    text = why if "Suggestion, check it" in why else f"Suggestion, check it. {why}"
    if suggest not in text:
        text = f"{text} A possible code is {suggest}."
    return text


def _rule_suggestion(text: str, transaction: Transaction, rules: Rules) -> tuple[str, str, str] | None:
    for item in rules.code_suggestions:
        if any_phrase(text, list(item.phrases)):
            return item.suggest, item.note, item.id
    return None


def _ai_code(transaction: Transaction, rows: list) -> tuple[str, str, str] | None:
    for row in rows:
        if not isinstance(row, dict):
            continue
        description = str(row.get("description") or "")
        suggest = str(row.get("suggest") or "").strip()
        if not description or not suggest:
            continue
        if not _same_text(description, transaction.description):
            continue
        why = str(row.get("why") or "A code was suggested from the wording.")
        return suggest, f"Suggestion, check it. {why}", "ai"
    return None


def _ai_personal(transaction: Transaction, rows: list) -> bool:
    for row in rows:
        if not isinstance(row, dict):
            continue
        description = str(row.get("description") or "")
        if description and _same_text(description, transaction.description):
            return True
    return False


def _already_an_error_hint(text: str, rules: Rules) -> bool:
    for group in rules.no_gst_groups:
        if any_phrase(text, list(group.phrases)):
            return True
    return False


def _same_code(current: str, suggested: str) -> bool:
    return _compact(current) == _compact(suggested)


def _same_text(left: str, right: str) -> bool:
    return _compact(left) == _compact(right)


def _compact(value: str) -> str:
    return " ".join(value.casefold().split())
