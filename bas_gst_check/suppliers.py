"""New suppliers and spend that jumped against the previous quarter."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from bas_gst_check.models import Flag, Transaction
from bas_gst_check.money import money_text
from bas_gst_check.rules import Rules
from bas_gst_check.sources import PURCHASES, SOURCE_TITLES


def purchase_totals(transactions: list[Transaction]) -> dict[str, Decimal]:
    """Inclusive purchases by supplier, using the spelling on the first line."""
    totals: dict[str, Decimal] = {}
    names: dict[str, str] = {}
    for transaction in transactions:
        if transaction.side != "purchase":
            continue
        key = transaction.contact.casefold().strip()
        if not key:
            continue
        names.setdefault(key, transaction.contact.strip())
        totals[key] = totals.get(key, Decimal("0")) + transaction.inclusive
    return {names[key]: amount for key, amount in totals.items()}


def account_totals(transactions: list[Transaction]) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = {}
    names: dict[str, str] = {}
    for transaction in transactions:
        if transaction.side != "purchase":
            continue
        key = transaction.account.casefold().strip()
        if not key:
            continue
        names.setdefault(key, transaction.account.strip())
        totals[key] = totals.get(key, Decimal("0")) + transaction.inclusive
    return {names[key]: amount for key, amount in totals.items()}


def supplier_flags(
    transactions: list[Transaction],
    previous: dict[str, Decimal] | None,
    rules: Rules,
) -> list[Flag]:
    if not previous:
        return []
    current = purchase_totals(transactions)
    previous_keys = {name.casefold(): amount for name, amount in previous.items()}
    flags: list[Flag] = []
    for name, amount in current.items():
        old = previous_keys.get(name.casefold())
        sample = _sample(transactions, name)
        if old is None:
            flags.append(_flag(
                "supplier_new",
                "New supplier",
                (
                    f"Suggestion, check it. {name} has purchases of {money_text(amount)} this quarter "
                    "and did not appear in the previous quarter."
                ),
                "Suggestion, check it. Confirm this supplier belongs in the business.",
                sample,
                name.casefold(),
            ))
            continue
        if old <= 0:
            continue
        percent = ((amount - old) / old) * Decimal(100)
        if percent >= rules.supplier_jump_percent and amount >= rules.supplier_jump_floor:
            flags.append(_flag(
                "supplier_jump",
                "Supplier spend jumped",
                (
                    f"Suggestion, check it. {name} is {money_text(amount)} this quarter, "
                    f"up from {money_text(old)} ({percent.quantize(Decimal('1'))}%). "
                    f"The review line is {rules.supplier_jump_percent}% and {money_text(rules.supplier_jump_floor)}."
                ),
                "Suggestion, check it. Confirm the extra spend is expected.",
                sample,
                name.casefold(),
            ))
    return flags


def load_history(path: Path) -> dict:
    if not path.is_file():
        return {"quarters": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"quarters": {}}
    if not isinstance(raw, dict) or not isinstance(raw.get("quarters"), dict):
        return {"quarters": {}}
    return raw


def remember_quarter(
    path: Path,
    period_key: str,
    purchases: dict[str, Decimal],
    accounts: dict[str, Decimal],
) -> None:
    history = load_history(path)
    history["quarters"][period_key] = {
        "purchases": {name: str(amount) for name, amount in purchases.items()},
        "accounts": {name: str(amount) for name, amount in accounts.items()},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, indent=2), encoding="utf-8")


def earlier_quarter(history: dict, period_key: str) -> tuple[dict[str, Decimal], dict[str, Decimal]] | None:
    quarters = history.get("quarters") or {}
    keys = [key for key in quarters if key != period_key and isinstance(quarters.get(key), dict)]
    if not keys:
        return None
    chosen = sorted(keys)[-1]
    block = quarters[chosen]
    return _money_map(block.get("purchases")), _money_map(block.get("accounts"))


def _money_map(raw: object) -> dict[str, Decimal]:
    if not isinstance(raw, dict):
        return {}
    found: dict[str, Decimal] = {}
    for name, amount in raw.items():
        try:
            found[str(name)] = Decimal(str(amount))
        except (ValueError, ArithmeticError):
            continue
    return found


def _sample(transactions: list[Transaction], supplier: str) -> Transaction | None:
    key = supplier.casefold()
    matches = [
        item for item in transactions
        if item.side == "purchase" and item.contact.casefold() == key
    ]
    if not matches:
        return None
    return max(matches, key=lambda item: item.inclusive)


def _flag(
    code: str,
    title: str,
    why: str,
    fix: str,
    transaction: Transaction | None,
    detail_key: str,
) -> Flag:
    return Flag(
        code=code,
        title=title,
        severity="review",
        why=why,
        fix=fix,
        source_url=PURCHASES,
        source_title=SOURCE_TITLES[PURCHASES],
        transaction=transaction,
        supplier_name="" if transaction else detail_key,
        detail_key=detail_key,
    )
