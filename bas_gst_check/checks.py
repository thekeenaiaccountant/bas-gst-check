"""Line checks. Each flag explains the likely mistake and a fix in plain English."""

from __future__ import annotations

from datetime import date

from bas_gst_check.models import Flag, Period, Severity, Transaction
from bas_gst_check.money import expected_gst, money_text
from bas_gst_check.rules import NoGstGroup, Rules
from bas_gst_check.sources import GST_CREDIT, GST_FREE, PURCHASES, SALES, SOURCE_TITLES, TAX_INVOICE
from bas_gst_check.summarise import recorded_as_capital
from bas_gst_check.textmatch import any_phrase

WORDING_HINT = " This is a hint from the wording, not a ruling."

CHECK_ORDER = (
    "unknown_side",
    "unknown_tax_code",
    "side_mismatch",
    "outside_period",
    "gst_amount",
    "usually_no_gst",
    "missing_gst",
    "bas_excluded_taxable",
    "duplicate",
    "capital_split",
    "bill_unreadable",
    "bill_no_abn",
    "bill_bad_checksum",
    "bill_several_abns",
    "bill_unmatched",
    "gst_on_bill",
    "gst_without_bill",
    "suggested_code",
    "personal_spend",
    "supplier_new",
    "supplier_jump",
    "abn_not_found",
    "abn_cancelled",
    "abn_not_gst_registered",
    "tax_invoice",
)


def run_checks(
    transactions: list[Transaction], period: Period | None, rules: Rules
) -> list[Flag]:
    flags: list[Flag] = []
    for transaction in transactions:
        flags.extend(_line_checks(transaction, period, rules))
    flags.extend(_duplicates(transactions))
    return flags


def _line_checks(transaction: Transaction, period: Period | None, rules: Rules) -> list[Flag]:
    flags: list[Flag] = []
    group = _no_gst_group(transaction, rules)
    charged = abs(transaction.gst) > rules.tolerance
    no_gst_hit = group is not None and (transaction.treatment == "taxable" or charged)

    if transaction.side == "unknown":
        flags.append(_flag(
            "unknown_side",
            "Sale or purchase is not clear",
            "error",
            "This line has no sale or purchase type, and the tax code does not say either. It was left out of the draft BAS totals.",
            "Mark it as a sale or a purchase. GST on Income is a sale. GST on Expenses is a purchase.",
            SALES,
            transaction,
        ))
    if transaction.treatment == "unknown":
        flags.append(_flag(
            "unknown_tax_code",
            "Tax code is not recognised",
            "error",
            f"The tax code '{transaction.tax_code_label}' is not one this check knows (GST on Income, GST on Expenses, GST Free, BAS Excluded, Input Taxed). The line was left out of the draft totals.",
            "Use the business's usual GST tax code so the line lands on the right BAS label.",
            SALES,
            transaction,
        ))
    if transaction.code_conflicts_with_side:
        flags.append(_flag(
            "side_mismatch",
            "Tax code and sale/purchase disagree",
            "error",
            "The tax code points to the other side of the BAS from the sale/purchase marker. The draft follows the sale/purchase marker.",
            "Change the tax code, or change the sale/purchase marker, so they agree.",
            SALES,
            transaction,
        ))
    if period and (transaction.date < period.start or transaction.date > period.end):
        flags.append(_flag(
            "outside_period",
            "Date is outside this period",
            "error",
            f"The date is {spoken_date(transaction.date)}, outside {spoken_date(period.start)} to {spoken_date(period.end)}. "
            "Cash accounting uses the date the money was received or paid. Accrual accounting uses the invoice or bill date, or the payment if that happened first.",
            "Move it into the period it belongs to, or take it out of this file.",
            SALES,
            transaction,
        ))
    if transaction.treatment == "taxable" and transaction.side != "unknown":
        expected = expected_gst(transaction.inclusive)
        gap = abs(transaction.gst - expected)
        if gap > rules.tolerance:
            flags.append(_flag(
                "gst_amount",
                "GST is not one-eleventh of the total",
                "error",
                f"GST on a taxable sale or purchase is one-eleventh of the GST-inclusive amount. "
                f"This line is {money_text(transaction.inclusive)} including GST, so the GST should be {money_text(expected)}. "
                f"The file shows {money_text(transaction.gst)} ({money_text(gap)} away). The review tolerance is {money_text(rules.tolerance)}.",
                f"Put the GST amount back to {money_text(expected)}, or change the tax code if this item should not have GST.",
                TAX_INVOICE,
                transaction,
            ))
    elif transaction.treatment in {"gst_free", "bas_excluded", "input_taxed"} and charged and group is None:
        flags.append(_flag(
            "gst_amount",
            "GST is recorded on a no-GST code",
            "error",
            f"This line is coded {transaction.tax_code_label}, which should not carry GST, but the file shows {money_text(transaction.gst)}.",
            "If the code is right, set the GST to zero. If GST really applies, use GST on Income or GST on Expenses.",
            TAX_INVOICE,
            transaction,
        ))
    if no_gst_hit:
        flags.append(_flag(
            "usually_no_gst",
            f"GST on {group.title.lower()}",
            "error",
            group.why + f" This line is coded {transaction.tax_code_label} with GST of {money_text(transaction.gst)}." + WORDING_HINT,
            "Code it GST Free, Input Taxed or BAS Excluded, as appropriate, and set the GST to zero so it does not inflate 1A or 1B.",
            group.source,
            transaction,
        ))
    if (
        transaction.side == "purchase"
        and transaction.treatment in {"gst_free", "input_taxed"}
        and not charged
        and group is None
        and _looks_taxable(transaction, rules)
    ):
        flags.append(_flag(
            "missing_gst",
            "Usually taxable expense has no GST",
            "error",
            "This looks like an expense that usually includes GST (rent, software, advertising and similar), but the code says there is none. "
            "That is right if the supplier is not registered for GST. It is a miss if they are." + WORDING_HINT,
            "If the supplier is registered, code it GST on Expenses and enter one-eleventh of the GST-inclusive price. If they are not registered, leave it and keep their invoice.",
            GST_FREE,
            transaction,
        ))
    if (
        transaction.treatment == "bas_excluded"
        and group is None
        and _looks_taxable(transaction, rules)
    ):
        flags.append(_flag(
            "bas_excluded_taxable",
            "BAS Excluded item looks taxable",
            "error",
            "BAS Excluded leaves a line off the BAS entirely. That fits wages, super, private drawings and transfers. This description looks like a real sale or expense." + WORDING_HINT,
            "Use GST on Income, GST on Expenses, GST Free or Input Taxed, whichever matches the tax invoice. Keep BAS Excluded for items that are not reported.",
            SALES,
            transaction,
        ))
    if _capital_miscode(transaction, rules):
        flags.append(_flag(
            "capital_split",
            "Capital purchase may belong at G10",
            "error",
            f"This looks like equipment or another capital item and it is {money_text(transaction.inclusive)} including GST, "
            f"over the {money_text(rules.capital_threshold)} review threshold. The account '{transaction.account}' is not a capital account, so the draft puts it at G11. "
            "Where capital purchases are not already split in the records, the ATO expects capital items costing more than $1,000 at G10. "
            "Simpler BAS (GST turnover under $10 million) does not lodge G10 and G11, but the split still keeps the file ready." + WORDING_HINT,
            "Move it to a capital or asset account if it is plant or equipment. Leave it in expenses if it is a repair, a hire or trading stock.",
            PURCHASES,
            transaction,
        ))
    if _claims_credit(transaction) and transaction.inclusive > rules.tax_invoice_threshold and not no_gst_hit:
        flags.append(_flag(
            "tax_invoice",
            "Tax invoice needed on file",
            "review",
            f"The GST-inclusive amount is {money_text(transaction.inclusive)}, more than {money_text(rules.tax_invoice_threshold)}, and this line claims a GST credit. "
            "The ATO requires a tax invoice before that credit is claimed. $82.50 or less can be supported by a receipt. This check cannot see your documents.",
            "Confirm a valid tax invoice is on file (supplier, ABN, date, what was bought, and the GST). If you do not have one, leave the credit out of this BAS.",
            GST_CREDIT,
            transaction,
        ))
    return flags


def _duplicates(transactions: list[Transaction]) -> list[Flag]:
    groups: dict[tuple, list[Transaction]] = {}
    for transaction in transactions:
        key = (
            transaction.side,
            transaction.date,
            transaction.contact.casefold(),
            transaction.description.casefold(),
            transaction.net,
            transaction.gst,
        )
        groups.setdefault(key, []).append(transaction)
    flags: list[Flag] = []
    for copies in groups.values():
        if len(copies) < 2:
            continue
        first = copies[0]
        for occurrence, extra in enumerate(copies[1:], start=2):
            flags.append(_flag(
                "duplicate",
                "Possible duplicate",
                "error",
                f"This matches row {first.row} ({first.date.isoformat()}, {first.contact}, {money_text(first.inclusive)}). Same date, contact, description and amounts. It may have been imported twice.",
                "Delete the extra copy if it is the same transaction. Keep both if they really are two separate supplies.",
                SALES,
                extra,
                detail_key=str(occurrence),
            ))
    return flags


def _capital_miscode(transaction: Transaction, rules: Rules) -> bool:
    if transaction.side != "purchase" or transaction.treatment in {"bas_excluded", "unknown"}:
        return False
    if transaction.inclusive <= rules.capital_threshold:
        return False
    if any_phrase(transaction.description, list(rules.not_capital_phrases)):
        return False
    if any_phrase(transaction.description, list(rules.capital_item_phrases)) is None:
        return False
    return not recorded_as_capital(transaction, rules)


def _claims_credit(transaction: Transaction) -> bool:
    return (
        transaction.side == "purchase"
        and transaction.treatment == "taxable"
        and transaction.gst > 0
    )


def _looks_taxable(transaction: Transaction, rules: Rules) -> bool:
    text = f"{transaction.description} {transaction.account}"
    return any_phrase(text, list(rules.usually_taxable_phrases)) is not None


def _no_gst_group(transaction: Transaction, rules: Rules) -> NoGstGroup | None:
    text = f"{transaction.description} {transaction.account}"
    for group in rules.no_gst_groups:
        if any_phrase(text, list(group.phrases)):
            return group
    return None


def _flag(
    code: str,
    title: str,
    severity: Severity,
    why: str,
    fix: str,
    source: str,
    transaction: Transaction,
    detail_key: str = "",
) -> Flag:
    return Flag(
        code=code,
        title=title,
        severity=severity,
        why=why,
        fix=fix,
        source_url=source,
        source_title=SOURCE_TITLES.get(source, "ATO guidance"),
        transaction=transaction,
        detail_key=detail_key,
    )


def spoken_date(value: date) -> str:
    return f"{value.day} {value.strftime('%B %Y')}"


def period_label(start: date, end: date) -> str:
    return f"{spoken_date(start)} to {spoken_date(end)}"
