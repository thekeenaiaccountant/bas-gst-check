"""Read a supplier ABN off the bill itself. Never guess a number."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from bas_gst_check.abn import abn_is_valid, digits_only
from bas_gst_check.models import Flag, Transaction
from bas_gst_check.money import parse_money
from bas_gst_check.sources import GST_CREDIT, SOURCE_TITLES

LABELLED_ABN = re.compile(
    r"(?i)\bA\s*\.?\s*B\s*\.?\s*N\s*\.?\b\s*[:#\-]?\s*((?:\d[\s]*){11})"
)
FROM_LINE = re.compile(r"(?im)^(?:from|supplier|biller)\s*:\s*(.+)$")
DATE_LINE = re.compile(r"(?im)^(?:invoice date|date)\s*:\s*(\d{4}-\d{2}-\d{2})")
TOTAL_LINE = re.compile(r"(?im)^(?:total|amount due|invoice total)\s*:\s*\$?\s*([0-9,]+(?:\.[0-9]{2})?)")
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".heic", ".heif"}
PDF_SUFFIXES = {".pdf"}


@dataclass
class BillReading:
    file_name: str
    supplier: str
    text: str
    unreadable: bool
    unreadable_reason: str = ""
    valid_abns: list[str] = field(default_factory=list)
    invalid_abns: list[str] = field(default_factory=list)
    bill_date: date | None = None
    total: Decimal | None = None
    used_confirmed: bool = False


@dataclass
class HardNote:
    supplier: str
    file_name: str
    reason: str
    detail: str


def extract_labelled_abns(text: str) -> tuple[list[str], list[str]]:
    """Return unique valid ABNs and unique checksum failures found next to an ABN label."""
    valid: list[str] = []
    invalid: list[str] = []
    for match in LABELLED_ABN.finditer(text or ""):
        digits = digits_only(match.group(1))
        if len(digits) != 11:
            continue
        if abn_is_valid(digits):
            if digits not in valid:
                valid.append(digits)
        elif digits not in invalid:
            invalid.append(digits)
    return valid, invalid


def abns_from_qr_payload(payload: str) -> tuple[list[str], list[str]]:
    """A QR may carry a labelled ABN, or be the 11 digits alone. Nothing else counts."""
    valid, invalid = extract_labelled_abns(payload)
    if valid or invalid:
        return valid, invalid
    compact = re.sub(r"\s", "", (payload or "").strip())
    digits = digits_only(compact)
    if compact == digits and len(digits) == 11:
        if abn_is_valid(digits):
            return [digits], []
        return [], [digits]
    return [], []


def read_bills(
    folder: Path,
    transactions: list[Transaction],
    *,
    readings_path: Path | None = None,
    confirmed: dict[str, str] | None = None,
    hints: dict[str, str] | None = None,
) -> tuple[list[Flag], list[HardNote], list[tuple[str, date | None, str, Transaction | None, str]]]:
    """Return warnings, hard-log rows, and ABNs safe to confirm with the ABR.

    The tuples are (abn, bill date, supplier, matched transaction or None, file name).
    """
    readings = _load_agent_readings(readings_path)
    flags: list[Flag] = []
    hard: list[HardNote] = []
    to_confirm: list[tuple[str, date | None, str, Transaction | None, str]] = []
    confirmed = confirmed or {}
    hints = hints or {}
    if not folder.is_dir():
        return flags, hard, to_confirm
    files = sorted(
        path for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES | PDF_SUFFIXES
    )
    for path in files:
        reading = _read_one(path, readings.get(path.name))
        _decide(reading, transactions, confirmed, hints, flags, hard, to_confirm)
    return flags, hard, to_confirm


def _decide(
    reading: BillReading,
    transactions: list[Transaction],
    confirmed: dict[str, str],
    hints: dict[str, str],
    flags: list[Flag],
    hard: list[HardNote],
    to_confirm: list[tuple[str, date | None, str, Transaction | None, str]],
) -> None:
    if reading.unreadable:
        _warn(
            flags, hard, reading, transactions, "bill_unreadable", "This bill could not be read",
            reading.unreadable_reason + _hint_note(reading, hints),
            "Ask Claude or Codex to read this file, or send a text PDF. No ABN was guessed.",
        )
        return
    if len(reading.valid_abns) > 1:
        shown = ", ".join(_grouped(number) for number in reading.valid_abns)
        _warn(
            flags, hard, reading, transactions, "bill_several_abns", "This bill shows more than one ABN",
            f"The bill shows more than one valid ABN ({shown}). None of them was used.",
            "Check which number is the supplier's ABN and say which one to confirm. Do not claim GST from a number you have not chosen.",
        )
        return
    if reading.invalid_abns and not reading.valid_abns:
        shown = ", ".join(_grouped(number) for number in reading.invalid_abns)
        _warn(
            flags, hard, reading, transactions, "bill_bad_checksum", "The ABN on this bill fails the checksum",
            f"The bill labels {shown} as an ABN, but it fails the official ABN checksum, so it cannot be a real ABN. It was not used.",
            "Read the digits again from the bill. If they still fail the checksum, ask the supplier for the ABN on their tax invoice.",
        )
        return
    if not reading.valid_abns:
        remembered = confirmed.get(_key(reading.supplier), "")
        if remembered and abn_is_valid(remembered):
            reading.used_confirmed = True
            _warn(
                flags, hard, reading, transactions, "bill_no_abn", "No ABN was printed on this bill",
                "No ABN was printed on this bill. The ABR check, if it is on, will use only the ABN you confirmed earlier for this supplier. That is a memory, not a number read from this page.",
                "If the bill should show an ABN, ask for a clearer copy. Otherwise leave the confirmed ABN as it is.",
            )
            _queue(reading, remembered, transactions, flags, hard, to_confirm)
            return
        _warn(
            flags, hard, reading, transactions, "bill_no_abn", "No ABN was found on this bill",
            "No ABN label with 11 digits was on this bill. No number was guessed." + _hint_note(reading, hints),
            "Look at the bill again, or tell me the ABN if you can see it and I will save it only after the checksum passes.",
        )
        return
    _queue(reading, reading.valid_abns[0], transactions, flags, hard, to_confirm)


def _queue(
    reading: BillReading,
    abn: str,
    transactions: list[Transaction],
    flags: list[Flag],
    hard: list[HardNote],
    to_confirm: list[tuple[str, date | None, str, Transaction | None, str]],
) -> None:
    matches = _match(reading, transactions)
    if not matches:
        _warn(
            flags, hard, reading, transactions, "bill_unmatched", "This bill did not match a transaction",
            f"The ABN {_grouped(abn)} was read from the bill, but no purchase matched the supplier, date and amount. It was not attached to a line.",
            "Check the supplier name, the invoice date and the total against the export. If the purchase is missing, it is not in this BAS file.",
        )
        to_confirm.append((abn, reading.bill_date, reading.supplier, None, reading.file_name))
        return
    for transaction in matches:
        to_confirm.append((abn, reading.bill_date or transaction.date, reading.supplier, transaction, reading.file_name))


def _match(reading: BillReading, transactions: list[Transaction]) -> list[Transaction]:
    strong: list[Transaction] = []
    for transaction in transactions:
        if transaction.side != "purchase":
            continue
        if not _same_supplier(reading.supplier, transaction.contact):
            continue
        amount_ok = reading.total is None or _same_money(reading.total, transaction)
        date_ok = reading.bill_date is None or reading.bill_date == transaction.date
        if amount_ok and date_ok:
            strong.append(transaction)
    if len(strong) <= 1:
        return strong
    signature = {(item.date, item.contact.casefold(), item.net, item.gst) for item in strong}
    if len(signature) == 1:
        return strong
    return []


def _warn(
    flags: list[Flag],
    hard: list[HardNote],
    reading: BillReading,
    transactions: list[Transaction],
    code: str,
    title: str,
    why: str,
    fix: str,
) -> None:
    matches = _match(reading, transactions)
    attached = matches[0] if len(matches) == 1 else None
    labelled = ""
    if len(reading.valid_abns) == 1:
        labelled = reading.valid_abns[0]
    elif len(reading.invalid_abns) == 1:
        labelled = reading.invalid_abns[0]
    flags.append(Flag(
        code=code,
        title=title,
        severity="error",
        why=f"{reading.file_name}: {why}",
        fix=fix,
        source_url=GST_CREDIT,
        source_title=SOURCE_TITLES[GST_CREDIT],
        transaction=attached,
        detail_key=reading.file_name,
        supplier_name=reading.supplier,
        line_date=reading.bill_date,
        line_amount=reading.total if reading.total is not None else (attached.inclusive if attached else None),
        line_gst=attached.gst if attached else None,
        line_abn=labelled,
    ))
    hard.append(HardNote(
        supplier=reading.supplier or "(supplier not named)",
        file_name=reading.file_name,
        reason=code,
        detail=why,
    ))


def _read_one(path: Path, agent: dict | None) -> BillReading:
    supplier = path.stem.replace("-", " ").replace("_", " ")
    if agent and agent.get("unreadable"):
        return BillReading(path.name, supplier, "", True, "The file was marked unreadable. No ABN was guessed.")
    text = ""
    if agent and str(agent.get("text") or "").strip():
        text = str(agent["text"])
    elif path.suffix.lower() in PDF_SUFFIXES:
        extracted = _pdf_text(path)
        if extracted is None:
            return BillReading(
                path.name, supplier, "", True,
                "This PDF could not be read here. A text PDF works best. A scan or photo can be read by Claude or Codex. No ABN was guessed.",
            )
        text = extracted
    elif path.suffix.lower() in IMAGE_SUFFIXES:
        extracted = _image_text(path)
        if not extracted:
            return BillReading(
                path.name, supplier, "", True,
                "This image could not be read here. Photos, HEIC and QR codes are clearest when Claude or Codex looks at the file. No ABN was guessed.",
            )
        text = extracted
    else:
        return BillReading(path.name, supplier, "", True, "This file type is not a PDF or a photo. No ABN was guessed.")
    if not text.strip():
        return BillReading(path.name, supplier, "", True, "No words could be read from this file. No ABN was guessed.")
    named = FROM_LINE.search(text)
    if named:
        supplier = named.group(1).strip()
    bill_date = None
    date_match = DATE_LINE.search(text)
    if date_match:
        bill_date = date.fromisoformat(date_match.group(1))
    total = None
    total_match = TOTAL_LINE.search(text)
    if total_match:
        try:
            total = parse_money(total_match.group(1))
        except ValueError:
            total = None
    valid, invalid = extract_labelled_abns(text)
    return BillReading(path.name, supplier, text, False, "", valid, invalid, bill_date, total)


def _pdf_text(path: Path) -> str | None:
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return None


def _image_text(path: Path) -> str | None:
    chunks: list[str] = []
    qr_payloads = _qr_payloads(path)
    if qr_payloads is None and not _ocr_available():
        return None
    for payload in qr_payloads or []:
        chunks.append(payload if re.search(r"(?i)\bABN\b", payload) else f"ABN: {payload}")
    ocr_text = _ocr(path)
    if ocr_text:
        chunks.append(ocr_text)
    if not chunks:
        return ""
    return "\n".join(chunks)


def _ocr_available() -> bool:
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return False
    return True


def _ocr(path: Path) -> str:
    if not _ocr_available():
        return ""
    import pytesseract
    from PIL import Image

    try:
        return pytesseract.image_to_string(Image.open(path)) or ""
    except Exception:
        return ""


def _qr_payloads(path: Path) -> list[str] | None:
    try:
        from PIL import Image
        from pyzbar.pyzbar import decode
    except ImportError:
        return None
    try:
        codes = decode(Image.open(path))
    except Exception:
        return []
    return [code.data.decode("utf-8", "replace") for code in codes]


def _load_agent_readings(path: Path | None) -> dict[str, dict]:
    if path is None or not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    rows = raw.get("readings") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        return {}
    found: dict[str, dict] = {}
    for row in rows:
        if isinstance(row, dict) and row.get("file"):
            found[str(row["file"])] = row
    return found


def _same_supplier(left: str, right: str) -> bool:
    a = _key(left)
    b = _key(right)
    if not a or not b:
        return False
    return a == b or a in b or b in a


def _same_money(total: Decimal, transaction: Transaction) -> bool:
    inclusive = transaction.inclusive.copy_abs() if hasattr(transaction.inclusive, "copy_abs") else abs(transaction.inclusive)
    return abs(inclusive - total) <= Decimal("0.05") or abs(abs(transaction.net) - total) <= Decimal("0.05")


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _grouped(number: str) -> str:
    digits = digits_only(number)
    if len(digits) != 11:
        return number
    return f"{digits[0:2]} {digits[2:5]} {digits[5:8]} {digits[8:11]}"


def _hint_note(reading: BillReading, hints: dict[str, str]) -> str:
    hint = hints.get(_key(reading.supplier), "")
    if not hint:
        return ""
    return f" Last time you said to look here first: {hint}."
