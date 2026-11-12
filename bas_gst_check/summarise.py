"""Draft BAS labels from the file as it stands. Suggested fixes are not applied."""

from __future__ import annotations

from decimal import Decimal

from bas_gst_check.models import Summary, Transaction
from bas_gst_check.money import cents
from bas_gst_check.rules import Rules
from bas_gst_check.textmatch import any_phrase

ZERO = Decimal("0.00")


def recorded_as_capital(transaction: Transaction, rules: Rules) -> bool:
    """G10 follows the account (or a GST-on-capital code), not a guess from the description."""
    if transaction.force_capital:
        return True
    return any_phrase(transaction.account, list(rules.capital_account_phrases)) is not None


def summarise(transactions: list[Transaction], rules: Rules) -> Summary:
    g1 = gst_on_sales = gst_on_purchases = g10 = g11 = ZERO
    sales = purchases = left_out = 0
    for transaction in transactions:
        if transaction.side == "unknown" or transaction.treatment == "unknown":
            left_out += 1
            continue
        inclusive = transaction.inclusive
        if transaction.side == "sale":
            sales += 1
            if transaction.treatment != "bas_excluded":
                g1 += inclusive
            if transaction.treatment == "taxable":
                gst_on_sales += transaction.gst
            continue
        purchases += 1
        if transaction.treatment == "bas_excluded":
            continue
        if recorded_as_capital(transaction, rules):
            g10 += inclusive
        else:
            g11 += inclusive
        if transaction.treatment == "taxable":
            gst_on_purchases += transaction.gst
    net = gst_on_sales - gst_on_purchases
    return Summary(
        g1=cents(g1),
        gst_on_sales=cents(gst_on_sales),
        gst_on_purchases=cents(gst_on_purchases),
        net=cents(net),
        g10=cents(g10),
        g11=cents(g11),
        sales_counted=sales,
        purchases_counted=purchases,
        left_out=left_out,
    )
