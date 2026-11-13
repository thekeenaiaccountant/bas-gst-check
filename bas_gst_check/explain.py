"""A short explanation of the draft net GST. Numbers only. No advice."""

from __future__ import annotations

from decimal import Decimal

from bas_gst_check.models import Summary
from bas_gst_check.money import money_text


def explain_bas(
    summary: Summary,
    current_suppliers: dict[str, Decimal],
    previous_suppliers: dict[str, Decimal] | None,
    current_accounts: dict[str, Decimal],
    previous_accounts: dict[str, Decimal] | None,
) -> str:
    net = money_text(abs(summary.net)) if summary.position != "nil" else money_text(summary.net)
    position = {"payable": "payable", "refundable": "refundable", "nil": "nil"}[summary.position]
    gap = summary.gst_on_purchases - summary.gst_on_sales
    if gap > 0:
        reason = f"1B is {money_text(gap)} higher than 1A, which is why the draft is a refund."
    elif gap < 0:
        reason = f"1A is {money_text(abs(gap))} higher than 1B, which is why the draft is payable."
    else:
        reason = "1A and 1B are equal, so the draft net GST is nil."
    lines = [f"Draft net GST is {net} {position}. {reason}"]
    if previous_suppliers:
        supplier = _largest_change(current_suppliers, previous_suppliers)
        account = _largest_change(current_accounts, previous_accounts or {})
        if supplier is not None:
            name, delta = supplier
            direction = "up" if delta > 0 else "down"
            sentence = (
                f"Against the previous quarter, the largest purchase change was {name}, "
                f"{direction} {money_text(abs(delta))}"
            )
            same_movement = account is not None and abs(account[1]) == abs(delta)
            if account is not None and account[0].casefold() != name.casefold() and not same_movement:
                account_name, account_delta = account
                account_direction = "up" if account_delta > 0 else "down"
                sentence += (
                    f", and the largest account change was {account_name}, "
                    f"{account_direction} {money_text(abs(account_delta))}"
                )
            lines.append(sentence + ".")
    return " ".join(lines)


def _largest_change(
    current: dict[str, Decimal],
    previous: dict[str, Decimal],
) -> tuple[str, Decimal] | None:
    previous_keys = {name.casefold(): (name, amount) for name, amount in previous.items()}
    best_name = ""
    best_delta = Decimal("0")
    seen: set[str] = set()
    for name, amount in current.items():
        key = name.casefold()
        seen.add(key)
        old = previous_keys.get(key, (name, Decimal("0")))[1]
        delta = amount - old
        if abs(delta) > abs(best_delta):
            best_name = name
            best_delta = delta
    for key, (name, old) in previous_keys.items():
        if key in seen:
            continue
        delta = Decimal("0") - old
        if abs(delta) > abs(best_delta):
            best_name = name
            best_delta = delta
    if not best_name or best_delta == 0:
        return None
    return best_name, best_delta
