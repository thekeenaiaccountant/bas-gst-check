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

SALE_TYPES = {"sale", "sales", "invoice", "receivable", "income", "credit"}
PURCHASE_TYPES = {"purchase", "purchases", "bill", "spend", "expense", "supplier"}


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
    return LoadedFile(errors=["Use a .json or .csv file."])


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
    if "date" not in mapping or "net" not in mapping or "gst" not in mapping or "tax_code" not in mapping:
        return LoadedFile(
            errors=[
                "The CSV needs columns for date, net amount, GST amount and tax code. "
                "Contact, description and account should be there too."
            ]
        )
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
        net = parse_money(row.get("net"))
        gst = parse_money(row.get("gst"))
    except (ValueError, KeyError) as exc:
        return None, f"Row {row_number}: {exc}"
    label = str(row.get("tax_code") or "").strip()
    if not label:
        return None, f"Row {row_number}: the tax code is blank."
    treatment, force_capital = _treatment(label)
    explicit = _explicit_side(str(row.get("type") or ""))
    contact = str(row.get("contact") or "").strip() or "No contact"
    description = str(row.get("description") or "").strip()
    account = str(row.get("account") or "").strip()
    side, conflict = _side(explicit, label, account, rules)
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


def _treatment(label: str) -> tuple[str, bool]:
    key = re.sub(r"[^a-z]", "", label.lower())
    if key in {"gstonincome"}:
        return "taxable", False
    if key in {"gstonexpenses"}:
        return "taxable", False
    if key in {"gstoncapital"}:
        return "taxable", True
    if key in {"gstfree", "gstfreeincome", "gstfreeexpenses", "freegst"}:
        return "gst_free", False
    if key in {"basexcluded", "basexclusions", "notreportable"}:
        return "bas_excluded", False
    if key in {"inputtaxed", "inputtaxedincome", "inputtaxedexpenses", "inputtaxedsales"}:
        return "input_taxed", False
    return "unknown", False


def _explicit_side(value: str) -> str:
    key = re.sub(r"[^a-z]", "", value.lower())
    if not key:
        return ""
    if key in SALE_TYPES:
        return "sale"
    if key in PURCHASE_TYPES:
        return "purchase"
    return "unknown"


def _side(explicit: str, label: str, account: str, rules: Rules) -> tuple[str, bool]:
    implied = _side_from_code(label)
    if explicit in {"sale", "purchase"}:
        return explicit, bool(implied and implied != explicit)
    if explicit == "unknown":
        return "unknown", False
    if implied:
        return implied, False
    sale = any_phrase(account, list(rules.sale_account_phrases))
    purchase = any_phrase(account, list(rules.purchase_account_phrases))
    if sale and not purchase:
        return "sale", False
    if purchase and not sale:
        return "purchase", False
    return "unknown", False


def _side_from_code(label: str) -> str:
    key = re.sub(r"[^a-z]", "", label.lower())
    if key == "gstonincome":
        return "sale"
    if key in {"gstonexpenses", "gstoncapital"}:
        return "purchase"
    return ""


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
