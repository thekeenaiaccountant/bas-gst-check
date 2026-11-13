"""Read a quarter of transactions from JSON or CSV."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from bas_gst_check.abn import digits_only
from bas_gst_check.models import Transaction
from bas_gst_check.money import parse_money
from bas_gst_check.rules import Rules
from bas_gst_check.textmatch import any_phrase

HEADER_ALIASES = {
    "date": "date",
    "transactiondate": "date",
    "datestring": "date",
    "type": "type",
    "source": "type",
    "transactiontype": "type",
    "contact": "contact",
    "name": "contact",
    "supplier": "contact",
    "customer": "contact",
    "contactname": "contact",
    "description": "description",
    "details": "description",
    "narration": "description",
    "memo": "description",
    "memodescription": "description",
    "reference": "reference",
    "invoice": "reference",
    "invoicenumber": "reference",
    "account": "account",
    "accountname": "account",
    "accountcode": "account",
    "net": "net",
    "netamount": "net",
    "amount": "net",
    "lineamount": "net",
    "subtotal": "net",
    "debit": "debit",
    "credit": "credit",
    "gross": "gross",
    "gst": "gst",
    "gstamount": "gst",
    "tax": "gst",
    "taxamount": "gst",
    "taxcode": "tax_code",
    "taxrate": "tax_code",
    "taxtype": "tax_code",
    "supplierabn": "supplier_abn",
    "abn": "supplier_abn",
    "capital": "capital",
    "iscapital": "capital",
    "g10": "capital",
}

SALE_TYPES = {
    "sale", "sales", "invoice", "receivable", "income", "credit",
    "salesinvoice", "salesreceipt", "receivemoney", "customerinvoice",
}
PURCHASE_TYPES = {
    "purchase", "purchases", "bill", "spend", "expense", "supplier",
    "spendmoney", "payableinvoice", "supplierbill", "cheque", "check",
    "expense", "billpayment",
}

# Plain names used by Xero, MYOB and QuickBooks Online Australia.
# treatment, capital flag, side hint ("" when the row must say sale or purchase).
CODE_TABLE = {
    "gst": ("taxable", False, ""),
    "gstonincome": ("taxable", False, "sale"),
    "output": ("taxable", False, "sale"),
    "gstonexpenses": ("taxable", False, "purchase"),
    "gstonnoncapital": ("taxable", False, "purchase"),
    "input": ("taxable", False, "purchase"),
    "gstoncapital": ("taxable", True, "purchase"),
    "gstoncapitalpurchases": ("taxable", True, "purchase"),
    "cap": ("taxable", True, "purchase"),
    "capexinput": ("taxable", True, "purchase"),
    "gstfree": ("gst_free", False, ""),
    "fre": ("gst_free", False, ""),
    "gstfreeincome": ("gst_free", False, "sale"),
    "gstfreeexpenses": ("gst_free", False, "purchase"),
    "exemptoutput": ("gst_free", False, "sale"),
    "exemptexpenses": ("gst_free", False, "purchase"),
    "exp": ("gst_free", False, "sale"),
    "exportsales": ("gst_free", False, "sale"),
    "nt": ("bas_excluded", False, ""),
    "basexcluded": ("bas_excluded", False, ""),
    "baseexcluded": ("bas_excluded", False, ""),
    "notreportable": ("bas_excluded", False, ""),
    "outofscope": ("bas_excluded", False, ""),
    "inp": ("input_taxed", False, ""),
    "inputtaxed": ("input_taxed", False, ""),
    "inputtax": ("input_taxed", False, ""),
    "its": ("input_taxed", False, "sale"),
}


@dataclass
class LoadedFile:
    transactions: list[Transaction] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    business_name: str = ""
    period_start: date | None = None
    period_end: date | None = None
    gst_basis: str = ""
    fictional: bool = False


def load_transactions(path: Path, rules: Rules) -> LoadedFile:
    if not path.is_file():
        return LoadedFile(errors=[f"I can't find {path.name}."])
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _load_json(path, rules)
    if suffix == ".csv":
        return _load_csv(path, rules)
    if suffix == ".xlsx":
        return _load_xlsx(path, rules)
    return LoadedFile(errors=[
        "Use a CSV, Excel (.xlsx), or JSON file. In Excel, you can also choose Save As and pick CSV."
    ])


def _load_json(path: Path, rules: Rules) -> LoadedFile:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return LoadedFile(errors=[f"The JSON could not be read ({exc.msg})."])
    loaded = LoadedFile()
    if isinstance(raw, list):
        rows = raw
    elif isinstance(raw, dict):
        loaded.business_name = str(raw.get("business_name") or "").strip()
        loaded.period_start = _optional_date(raw.get("period_start"), "period_start", loaded.errors)
        loaded.period_end = _optional_date(raw.get("period_end"), "period_end", loaded.errors)
        loaded.gst_basis = str(raw.get("gst_basis") or "").strip().lower()
        loaded.fictional = bool(raw.get("fictional"))
        rows = raw.get("transactions")
        if not isinstance(rows, list):
            loaded.errors.append("The JSON needs a transactions list.")
            return loaded
    else:
        return LoadedFile(errors=["The JSON should be a list of transactions, or an object with a transactions list."])
    if not rows and not loaded.errors:
        loaded.errors.append("The file has no transactions.")
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            loaded.errors.append(f"Row {index} is not an object.")
            continue
        transaction, error = _transaction_from_mapping(index, _normalise_row(row), rules)
        if error:
            loaded.errors.append(error)
        elif transaction:
            loaded.transactions.append(transaction)
    return loaded


def _load_csv(path: Path, rules: Rules) -> LoadedFile:
    loaded = LoadedFile()
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return LoadedFile(errors=["The CSV needs to be UTF-8."])
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        return LoadedFile(errors=["The CSV has no header row."])
    mapping = {_normalise_header(name): name for name in reader.fieldnames if name}
    if not _headers_are_usable(mapping):
        return LoadedFile(errors=[_missing_column_message("CSV")])
    rows = list(reader)
    if not rows:
        return LoadedFile(errors=["The file has no transactions."])
    for index, row in enumerate(rows, start=2):
        flattened = {logical: (row.get(original) or "") for logical, original in mapping.items()}
        transaction, error = _transaction_from_mapping(index, flattened, rules)
        if error:
            loaded.errors.append(error)
        elif transaction:
            loaded.transactions.append(transaction)
    return loaded


def _transaction_from_mapping(
    row_number: int, row: dict, rules: Rules
) -> tuple[Transaction | None, str | None]:
    try:
        when = _parse_date(row.get("date"))
        net, gst, amount_side = _amounts(row)
    except (ValueError, KeyError) as exc:
        return None, f"Row {row_number}: {exc}"
    label = str(row.get("tax_code") or "").strip()
    if not label:
        return None, f"Row {row_number}: the tax code is blank."
    treatment, force_capital, code_side = _treatment(label)
    explicit = _explicit_side(str(row.get("type") or "")) or amount_side
    contact = str(row.get("contact") or "").strip() or "No contact"
    description = str(row.get("description") or "").strip()
    account = str(row.get("account") or "").strip()
    side, conflict = _side(explicit, code_side, account, rules)
    if not description:
        description = "(no description)"
    return (
        Transaction(
            row=row_number,
            date=when,
            side=side,
            treatment=treatment,
            tax_code_label=label,
            contact=contact,
            description=description,
            account=account or "(no account)",
            net=net,
            gst=gst,
            supplier_abn=digits_only(str(row.get("supplier_abn") or "")),
            reference=str(row.get("reference") or "").strip(),
            force_capital=force_capital or _yes(row.get("capital")),
            code_conflicts_with_side=conflict,
        ),
        None,
    )


def _load_xlsx(path: Path, rules: Rules) -> LoadedFile:
    try:
        import openpyxl
    except ImportError:
        return LoadedFile(errors=[
            "This is an Excel file. Ask the app to install the free reader, "
            "or in Excel choose File, Save As, and pick CSV."
        ])
    try:
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception:
        return LoadedFile(errors=["The Excel file could not be opened. Try Save As CSV."])
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    workbook.close()
    if not rows:
        return LoadedFile(errors=["The Excel file has no rows."])
    headers = [str(cell).strip() if cell is not None else "" for cell in rows[0]]
    mapping = {_normalise_header(name): index for index, name in enumerate(headers) if name}
    if not _headers_are_usable(mapping):
        return LoadedFile(errors=[_missing_column_message("Excel")])
    if len(rows) < 2:
        return LoadedFile(errors=["The file has no transactions."])
    loaded = LoadedFile()
    for index, raw in enumerate(rows[1:], start=2):
        if raw is None or all(cell in (None, "") for cell in raw):
            continue
        flattened = {}
        for logical, column in mapping.items():
            value = raw[column] if column < len(raw) else ""
            flattened[logical] = "" if value is None else value
        transaction, error = _transaction_from_mapping(index, flattened, rules)
        if error:
            loaded.errors.append(error)
        elif transaction:
            loaded.transactions.append(transaction)
    if not loaded.transactions and not loaded.errors:
        loaded.errors.append("The file has no transactions.")
    return loaded


def _headers_are_usable(mapping: dict) -> bool:
    has_amount = "net" in mapping or "debit" in mapping or "credit" in mapping or "gross" in mapping
    return "date" in mapping and "tax_code" in mapping and "gst" in mapping and has_amount


def _missing_column_message(kind: str) -> str:
    return (
        f"This {kind} needs a date, a tax code, and amounts. "
        "Amounts can be net and GST, or debit and credit with a tax column. "
        "Contact, description and account should be there too. "
        "If this came from Excel, you can also choose File, Save As, and pick CSV."
    )


def _amounts(row: dict) -> tuple[Decimal, Decimal, str]:
    gst = parse_money(row.get("gst")) if _filled(row.get("gst")) else None
    if _filled(row.get("net")):
        return parse_money(row.get("net")), gst if gst is not None else Decimal("0"), ""
    debit = parse_money(row.get("debit")) if _filled(row.get("debit")) else Decimal("0")
    credit = parse_money(row.get("credit")) if _filled(row.get("credit")) else Decimal("0")
    if debit or credit:
        if debit and not credit:
            return debit, gst if gst is not None else Decimal("0"), "purchase"
        if credit and not debit:
            return credit, gst if gst is not None else Decimal("0"), "sale"
        if debit >= credit:
            return debit - credit, gst if gst is not None else Decimal("0"), "purchase"
        return credit - debit, gst if gst is not None else Decimal("0"), "sale"
    if _filled(row.get("gross")) and gst is not None:
        return parse_money(row.get("gross")) - gst, gst, ""
    raise ValueError("the amount is blank")


def _filled(value: object) -> bool:
    return value not in (None, "") and str(value).strip() != ""


def _treatment(label: str) -> tuple[str, bool, str]:
    key = re.sub(r"[^a-z]", "", label.lower())
    if key in CODE_TABLE:
        treatment, capital, side = CODE_TABLE[key]
        return treatment, capital, side
    return "unknown", False, ""


def _explicit_side(value: str) -> str:
    key = re.sub(r"[^a-z]", "", value.lower())
    if key in SALE_TYPES:
        return "sale"
    if key in PURCHASE_TYPES:
        return "purchase"
    return ""


def _side(explicit: str, code_side: str, account: str, rules: Rules) -> tuple[str, bool]:
    implied = code_side if code_side in {"sale", "purchase"} else ""
    if explicit in {"sale", "purchase"}:
        return explicit, bool(implied and implied != explicit)
    if implied:
        return implied, False
    sale = any_phrase(account, list(rules.sale_account_phrases))
    purchase = any_phrase(account, list(rules.purchase_account_phrases))
    if sale and not purchase:
        return "sale", False
    if purchase and not sale:
        return "purchase", False
    return "unknown", False


def _yes(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"yes", "y", "true", "1", "capital", "g10"}


def _parse_date(value: object) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        raise ValueError("the date is blank")
    for parser in (
        lambda raw: date.fromisoformat(raw[:10]),
        lambda raw: datetime.strptime(raw, "%d/%m/%Y").date(),
        lambda raw: datetime.strptime(raw, "%d-%m-%Y").date(),
        lambda raw: datetime.strptime(raw, "%d %b %Y").date(),
    ):
        try:
            return parser(text)
        except ValueError:
            continue
    raise ValueError(f"the date '{text}' needs to look like 2026-07-15")


def _optional_date(value: object, label: str, errors: list[str]) -> date | None:
    if value in (None, ""):
        return None
    try:
        return _parse_date(value)
    except ValueError as exc:
        errors.append(f"{label}: {exc}")
        return None


def _normalise_row(row: dict) -> dict:
    normalised: dict[str, object] = {}
    for key, value in row.items():
        normalised[_normalise_header(str(key))] = value
    return normalised


def _normalise_header(name: str) -> str:
    compact = re.sub(r"[^a-z0-9]", "", name.lower())
    return HEADER_ALIASES.get(compact, compact)
