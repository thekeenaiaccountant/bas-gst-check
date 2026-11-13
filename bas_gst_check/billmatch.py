"""Match bills to export lines and compare the GST. Maths only. Nothing is sent."""

from __future__ import annotations

from bas_gst_check.billread import BillReading, _date_ok, _same_money, _same_supplier
from bas_gst_check.models import Flag, Transaction
from bas_gst_check.money import money_text
from bas_gst_check.rules import Rules
from bas_gst_check.sources import GST_CREDIT, SOURCE_TITLES


def compare_bills(
    readings: list[BillReading],
    transactions: list[Transaction],
    rules: Rules,
) -> list[Flag]:
    """GST claimed with no bill, a bill with no line, and GST that does not match."""
    readable = [reading for reading in readings if not reading.unreadable and reading.total is not None]
    if not readable:
        return []
    pairs = _assign(readable, transactions, rules)
    matched_ids = {id(transaction) for _reading, transaction in pairs}
    covered = {
        (item.date, item.contact.casefold(), item.description.casefold(), item.net, item.gst)
        for _reading, item in pairs
    }
    flags: list[Flag] = []
    for reading, transaction in pairs:
        if reading.gst is None:
            continue
        gap = abs(reading.gst - transaction.gst)
        if gap <= rules.tolerance:
            continue
        bill_abn = reading.valid_abns[0] if len(reading.valid_abns) == 1 else ""
        flags.append(_flag(
            "gst_on_bill",
            "GST on the bill differs from the file",
            (
                f"The bill shows GST of {money_text(reading.gst)}. "
                f"The file shows {money_text(transaction.gst)}. "
                f"The difference is {money_text(gap)}, over the {money_text(rules.tolerance)} tolerance."
            ),
            "Use the GST printed on the bill, or fix the bill if the file is already right.",
            transaction,
            reading.file_name,
            bill_abn,
        ))
    for transaction in transactions:
        if not _claims_gst(transaction):
            continue
        if id(transaction) in matched_ids:
            continue
        signature = (
            transaction.date,
            transaction.contact.casefold(),
            transaction.description.casefold(),
            transaction.net,
            transaction.gst,
        )
        if signature in covered:
            continue
        flags.append(_flag(
            "gst_without_bill",
            "GST claimed and no bill matched",
            (
                f"This line claims GST of {money_text(transaction.gst)} "
                f"on {money_text(transaction.inclusive)}. No bill in the folder matched the supplier, date and amount."
            ),
            "Add the bill to the folder, or take the GST out of 1B until the bill is on file.",
            transaction,
            transaction.reference,
            "",
        ))
    return flags


def _assign(
    readings: list[BillReading],
    transactions: list[Transaction],
    rules: Rules,
) -> list[tuple[BillReading, Transaction]]:
    candidates: list[tuple[int, BillReading, Transaction]] = []
    for reading in readings:
        for transaction in transactions:
            if transaction.side != "purchase":
                continue
            if not _same_supplier(reading.supplier, transaction.contact):
                continue
            if reading.total is None or not _same_money(reading.total, transaction, rules):
                continue
            if not _date_ok(reading, transaction, rules):
                continue
            exact_date = int(reading.bill_date == transaction.date)
            candidates.append((exact_date, reading, transaction))
    candidates.sort(key=lambda item: item[0], reverse=True)
    used_readings: set[int] = set()
    used_transactions: set[int] = set()
    pairs: list[tuple[BillReading, Transaction]] = []
    for _score, reading, transaction in candidates:
        if id(reading) in used_readings or id(transaction) in used_transactions:
            continue
        used_readings.add(id(reading))
        used_transactions.add(id(transaction))
        pairs.append((reading, transaction))
    return pairs


def _claims_gst(transaction: Transaction) -> bool:
    return transaction.side == "purchase" and transaction.gst > 0


def _flag(
    code: str,
    title: str,
    why: str,
    fix: str,
    transaction: Transaction,
    detail_key: str,
    line_abn: str,
) -> Flag:
    return Flag(
        code=code,
        title=title,
        severity="error",
        why=why,
        fix=fix,
        source_url=GST_CREDIT,
        source_title=SOURCE_TITLES[GST_CREDIT],
        transaction=transaction,
        detail_key=detail_key,
        line_abn=line_abn,
    )
