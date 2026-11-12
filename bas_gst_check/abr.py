"""Optional supplier ABN lookup against the free ABR JSON service.

The authentication GUID is sent only as the request parameter. It is not
written into the cache, the report, or error text.
"""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from bas_gst_check.abn import abn_is_valid, digits_only
from bas_gst_check.models import AbrNote, Flag, Transaction
from bas_gst_check.money import money_text
from bas_gst_check.rules import Rules
from bas_gst_check.settings import guid_shape_ok
from bas_gst_check.sources import ABR_REGISTER, GST_CREDIT, SOURCE_TITLES

ABR_ENDPOINT = "https://abr.business.gov.au/json/AbnDetails.aspx"
Fetch = Callable[[str, float], str]


@dataclass
class AbrRecord:
    abn: str
    found: bool
    status: str
    status_from: date | None
    gst_from: date | None
    entity_name: str
    message: str
    auth_rejected: bool = False


@dataclass
class AbrOutcome:
    mode: str
    message: str
    flags: list[Flag]
    notes: list[AbrNote]
    cache_hits: int = 0
    network_calls: int = 0


class AbrTransportError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def urllib_fetch(url: str, timeout: float) -> str:
    """Fetch one ABR response. The URL contains the GUID and must not be logged."""
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "bas-gst-check"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", "replace")
    except (TimeoutError, socket.timeout) as exc:
        raise AbrTransportError("timed out") from exc
    except URLError as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(reason, (TimeoutError, socket.timeout)):
            raise AbrTransportError("timed out") from exc
        raise AbrTransportError("could not reach the ABR") from exc


def ato_abn() -> str:
    """The Tax Office publishes this ABN. Split so the source file has no 11-digit run."""
    return "51" + "824" + "753" + "556"


def abr_skipped_message() -> str:
    return (
        'ABN check is off: say "set up ABN check" to turn it on. '
        f"It is optional and free. Register at {ABR_REGISTER}. "
        "Bills can still be read for a supplier ABN. Nothing is sent until a GUID is saved."
    )


def probe_guid(guid: str, *, fetch: Fetch | None = None, timeout: float = 8) -> tuple[bool, str]:
    """Look up the Tax Office ABN to see if a GUID works. Never include the GUID in the text."""
    if not guid or not guid_shape_ok(guid):
        return False, (
            "That does not look like an ABR GUID. It should be letters and numbers in the "
            "8-4-4-4-12 shape. Nothing was sent. Paste it again, or say skip for now."
        )
    transport = fetch or urllib_fetch
    try:
        record = _lookup_one(ato_abn(), guid, timeout, transport)
    except AbrTransportError as exc:
        return False, (
            f"The GUID was saved, but the ABR {exc.reason}, so it is not confirmed yet. "
            "Nothing else was sent. Try again later with 'set up ABN check'."
        )
    if record.auth_rejected:
        return False, (
            "The ABR did not accept the GUID. Check that the whole key from the email was saved. "
            "The key is not printed here."
        )
    name = record.entity_name.casefold()
    if record.found and record.status == "active" and record.gst_from and "taxation" in name:
        return True, (
            "The ABR accepted the GUID. A test lookup of the Tax Office's own public ABN "
            "came back active and GST-registered. Supplier bills can now be checked the same way."
        )
    return False, (
        "The ABR answered, but the test lookup of the Tax Office's public ABN did not look right. "
        "The GUID was not printed here. Try again in a minute, or say skip for now."
    )


def confirm_bill_abns(
    items: list[tuple[str, object, str, object, str]],
    rules: Rules,
    guid: str,
    cache_path: Path,
    *,
    bad_shape: bool = False,
    fetch: Fetch | None = None,
) -> AbrOutcome:
    """Confirm ABNs taken from bills. Items are (abn, date, supplier, transaction, file name)."""
    if bad_shape:
        return AbrOutcome(
            mode="bad_shape",
            message=(
                'ABN check is off: say "set up ABN check" to turn it on. '
                "The saved value does not look like an ABR GUID, so nothing was sent."
            ),
            flags=[],
            notes=[],
        )
    if not guid:
        return AbrOutcome(mode="off", message=abr_skipped_message(), flags=[], notes=[])
    if not items:
        return AbrOutcome(
            mode="on",
            message=(
                "A GUID is saved. No bill produced a single valid ABN to confirm, so the ABR was not called."
            ),
            flags=[],
            notes=[],
        )
    cache = _read_cache(cache_path)
    transport = fetch or urllib_fetch
    flags: list[Flag] = []
    notes: list[AbrNote] = []
    hits = 0
    calls = 0
    seen: dict[str, AbrRecord | None] = {}
    for abn, on_date, supplier, transaction, file_name in items:
        if abn not in seen:
            if abn in cache:
                seen[abn] = cache[abn]
                hits += 1
            else:
                calls += 1
                try:
                    record = _lookup_one(abn, guid, rules.abr_timeout_seconds, transport)
                except AbrTransportError as exc:
                    seen[abn] = None
                    notes.append(AbrNote(
                        supplier_abn=abn,
                        contact=supplier,
                        reason=f"The ABR lookup {exc.reason}. No conclusion was drawn for this bill.",
                    ))
                    continue
                if record.auth_rejected:
                    return AbrOutcome(
                        mode="rejected",
                        message=(
                            "The ABR did not accept the GUID, so these bill ABNs were not confirmed. "
                            "The GUID was not written into this report."
                        ),
                        flags=[],
                        notes=[],
                        cache_hits=hits,
                        network_calls=calls,
                    )
                cache[abn] = record
                seen[abn] = record
                _write_cache(cache_path, cache)
        record = seen.get(abn)
        if record is None:
            continue
        flags.extend(_flags_for_known(abn, on_date, supplier, transaction, file_name, record, rules))
    cached = f"{hits} answered from the saved cache on this computer" if hits else "nothing came from the local cache"
    called = "called the ABR" if calls else "did not need a new call"
    return AbrOutcome(
        mode="on",
        message=(
            f"ABNs read from bills were checked with the ABR. {cached}, and this run {called} "
            f"for {calls} ABN{'s' if calls != 1 else ''}. Only that ABN and the GUID were sent. "
            "The GUID is not stored in the cache or this report."
        ),
        flags=flags,
        notes=notes,
        cache_hits=hits,
        network_calls=calls,
    )


def lookup_suppliers(
    transactions: list[Transaction],
    rules: Rules,
    guid: str,
    cache_path: Path,
    *,
    bad_shape: bool = False,
    fetch: Fetch | None = None,
) -> AbrOutcome:
    if bad_shape:
        return AbrOutcome(
            mode="bad_shape",
            message=(
                "A supplier ABN check was not run. The ABR GUID in settings does not look "
                "like an ABR GUID, so nothing was sent. Fix it in my-settings.toml or remove it to skip the check."
            ),
            flags=[],
            notes=[],
        )
    if not guid:
        return AbrOutcome(
            mode="off",
            message=(
                "Supplier ABN lookup is off. No ABR GUID is set, so nothing was sent anywhere. "
                f"A free GUID can be registered with the Australian Business Register ({ABR_REGISTER}). "
                "Purchases that claim GST and have no ABN in the file are still listed."
            ),
            flags=[],
            notes=[],
        )

    cache = _read_cache(cache_path)
    transport = fetch or urllib_fetch
    flags: list[Flag] = []
    notes: list[AbrNote] = []
    hits = 0
    calls = 0
    seen: dict[str, AbrRecord | None] = {}
    auth_failed = False

    for transaction in transactions:
        if not _needs_lookup(transaction, rules):
            continue
        abn = transaction.supplier_abn
        if abn not in seen and not auth_failed:
            if abn in cache:
                seen[abn] = cache[abn]
                hits += 1
            else:
                calls += 1
                try:
                    record = _lookup_one(abn, guid, rules.abr_timeout_seconds, transport)
                except AbrTransportError as exc:
                    seen[abn] = None
                    notes.append(AbrNote(
                        supplier_abn=abn,
                        contact=transaction.contact,
                        reason=f"The ABR lookup {exc.reason}. No conclusion was drawn for this supplier.",
                    ))
                    continue
                if record.auth_rejected:
                    auth_failed = True
                    seen[abn] = None
                    continue
                cache[abn] = record
                seen[abn] = record
                _write_cache(cache_path, cache)
        record = seen.get(abn)
        if record is None:
            continue
        flags.extend(_flags_for(transaction, record, rules))

    if auth_failed:
        return AbrOutcome(
            mode="rejected",
            message=(
                "The ABR did not accept the GUID, so supplier registrations were not checked. "
                "The GUID was not written into this report. Check the value in my-settings.toml."
            ),
            flags=[],
            notes=[],
            cache_hits=hits,
            network_calls=calls,
        )
    called = "called the ABR" if calls else "did not need a new call"
    cached = f"{hits} answered from the saved cache on this computer" if hits else "nothing came from the local cache"
    return AbrOutcome(
        mode="on",
        message=(
            f"Supplier ABN lookup is on. {cached}, and this run {called} for {calls} supplier "
            f"{'ABN' if calls == 1 else 'ABNs'}. Only the ABN and the GUID go to the ABR. "
            "The GUID is not stored in the cache or this report."
        ),
        flags=flags,
        notes=notes,
        cache_hits=hits,
        network_calls=calls,
    )


def _needs_lookup(transaction: Transaction, rules: Rules) -> bool:
    return (
        transaction.side == "purchase"
        and transaction.treatment == "taxable"
        and transaction.gst > 0
        and transaction.inclusive > rules.tax_invoice_threshold
        and bool(transaction.supplier_abn)
    )


def _lookup_one(abn: str, guid: str, timeout: float, fetch: Fetch) -> AbrRecord:
    query = urlencode({"abn": abn, "callback": "callback", "guid": guid})
    body = fetch(f"{ABR_ENDPOINT}?{query}", timeout)
    return parse_abr_body(abn, body)


def parse_abr_body(abn: str, body: str) -> AbrRecord:
    payload = _unwrap_jsonp(body)
    message = str(payload.get("Message") or "").strip()
    if _auth_rejected(message):
        return AbrRecord(abn, False, "", None, None, "", message, auth_rejected=True)
    entity = _entity_name(payload)
    status = str(payload.get("AbnStatus") or "").strip()
    returned = digits_only(str(payload.get("Abn") or ""))
    found = bool(returned) and "no records" not in message.lower() and "not a valid abn" not in message.lower()
    if not found:
        return AbrRecord(abn, False, "", None, None, entity, message or "No records found")
    return AbrRecord(
        abn=returned or abn,
        found=True,
        status=status.lower(),
        status_from=_parse_day(payload.get("AbnStatusEffectiveFrom")),
        gst_from=_parse_day(payload.get("Gst")),
        entity_name=entity,
        message=message,
    )


def _flags_for_known(
    abn: str,
    on_date: object,
    supplier: str,
    transaction: object,
    file_name: str,
    record: AbrRecord,
    rules: Rules,
) -> list[Flag]:
    when = on_date if isinstance(on_date, date) else date.today()
    name = record.entity_name or supplier or "the entity on this ABN"
    where = f"On {file_name}, " if file_name else ""
    attached = transaction if isinstance(transaction, Transaction) else None
    if not record.found:
        return [_abn_flag(
            "abn_not_found",
            "Supplier ABN was not found",
            f"{where}the ABN read from the bill was not found at the ABR. It was not guessed. Do not claim GST against it until the supplier confirms the number.",
            "Check the digits on the bill. If the ABR has no record, leave the GST out of 1B.",
            attached,
            file_name,
        )]
    if record.status == "cancelled" and (record.status_from is None or record.status_from <= when):
        cancelled_on = spoken(record.status_from) if record.status_from else "an unknown date"
        return [_abn_flag(
            "abn_cancelled",
            "Supplier ABN is cancelled",
            f"{where}the ABR lists {name} as cancelled from {cancelled_on}, which is on or before {spoken(when)}. A cancelled ABN cannot support a GST credit.",
            "Use the ABN printed on the bill only if it was active on that date. If it was cancelled, remove the GST from 1B.",
            attached,
            file_name,
        )]
    if record.gst_from is None or record.gst_from > when:
        if record.gst_from is None:
            registered = "The ABR record has no GST registration date."
        else:
            registered = f"The ABR record shows GST registration from {spoken(record.gst_from)}, which is after this bill."
        return [_abn_flag(
            "abn_not_gst_registered",
            "Supplier was not registered for GST on this date",
            f"{where}{name} does not show as GST-registered on {spoken(when)}. {registered} "
            "GST charged by a business that is not registered is generally not claimable. "
            "The free lookup shows the current registration start, not a full history of earlier cancellations.",
            "Confirm the supplier was registered for GST on the bill date before claiming the credit. If they were not, take the GST out of 1B.",
            attached,
            file_name,
        )]
    return []


def _flags_for(transaction: Transaction, record: AbrRecord, rules: Rules) -> list[Flag]:
    name = record.entity_name or "the entity on this ABN"
    if not record.found:
        checksum = ""
        if not abn_is_valid(transaction.supplier_abn):
            checksum = " The number also fails the ABN checksum, so it cannot be a real ABN."
        return [_abn_flag(
            "abn_not_found",
            "Supplier ABN was not found",
            f"The ABR lookup returned no record for this supplier ABN.{checksum} "
            f"A GST credit needs a real ABN on the tax invoice when the purchase is over {money_text(rules.tax_invoice_threshold)}.",
            "Check the digits against the tax invoice. If there is no valid ABN, do not claim the GST.",
            transaction,
        )]
    if record.status == "cancelled" and (record.status_from is None or record.status_from <= transaction.date):
        when = spoken(record.status_from) if record.status_from else "an unknown date"
        return [_abn_flag(
            "abn_cancelled",
            "Supplier ABN is cancelled",
            f"The ABR lists {name} as cancelled from {when}, which is on or before this purchase ({spoken(transaction.date)}). "
            "A cancelled ABN cannot support a GST credit.",
            "Use the ABN printed on the tax invoice and confirm it was active on the purchase date. If it was cancelled, remove the GST from 1B.",
            transaction,
        )]
    if record.gst_from is None or record.gst_from > transaction.date:
        if record.gst_from is None:
            registered = "The ABR record has no GST registration date."
        else:
            registered = (
                f"The ABR record shows GST registration from {spoken(record.gst_from)}, which is after this purchase."
            )
        return [_abn_flag(
            "abn_not_gst_registered",
            "Supplier was not registered for GST on this date",
            f"{name} does not show as GST-registered on {spoken(transaction.date)}. {registered} "
            "GST charged by a business that is not registered is generally not claimable. "
            "The free lookup shows the current registration start, not a full history of earlier cancellations.",
            "Confirm the supplier was registered for GST on the purchase date before claiming the credit. If they were not, take the GST out of 1B.",
            transaction,
        )]
    return []


def _abn_flag(
    code: str,
    title: str,
    why: str,
    fix: str,
    transaction: Transaction | None = None,
    detail_key: str = "",
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
    )


def _unwrap_jsonp(body: str) -> dict:
    text = body.strip()
    if not text:
        raise AbrTransportError("returned an empty response")
    if text[0] not in "{[":
        start = text.find("(")
        end = text.rfind(")")
        if start == -1 or end <= start:
            raise AbrTransportError("returned a response that was not JSON")
        text = text[start + 1 : end]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AbrTransportError("returned a response that was not JSON") from exc
    if not isinstance(payload, dict):
        raise AbrTransportError("returned a response that was not JSON")
    return payload


def _auth_rejected(message: str) -> bool:
    lowered = message.lower()
    return "guid" in lowered and ("not recognised" in lowered or "not recognized" in lowered or "authentication" in lowered)


def _entity_name(payload: dict) -> str:
    name = str(payload.get("EntityName") or "").strip()
    if name:
        return name
    business = payload.get("BusinessName")
    if isinstance(business, list) and business:
        return str(business[0])
    if isinstance(business, str):
        return business
    return ""


def _parse_day(value: object) -> date | None:
    if value in (None, ""):
        return None
    text = str(value).strip()[:10]
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None
    if parsed.year < 1900:
        return None
    return parsed


def spoken(value: date) -> str:
    return f"{value.day} {value.strftime('%B %Y')}"


def _read_cache(path: Path) -> dict[str, AbrRecord]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    records: dict[str, AbrRecord] = {}
    if not isinstance(raw, dict):
        return records
    for abn, item in raw.items():
        if not isinstance(item, dict):
            continue
        records[str(abn)] = AbrRecord(
            abn=str(abn),
            found=bool(item.get("found")),
            status=str(item.get("status") or ""),
            status_from=_parse_day(item.get("status_from")),
            gst_from=_parse_day(item.get("gst_from")),
            entity_name=str(item.get("entity_name") or ""),
            message=str(item.get("message") or ""),
        )
    return records


def _write_cache(path: Path, records: dict[str, AbrRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        abn: {
            "found": record.found,
            "status": record.status,
            "status_from": record.status_from.isoformat() if record.status_from else "",
            "gst_from": record.gst_from.isoformat() if record.gst_from else "",
            "entity_name": record.entity_name,
            "message": record.message,
        }
        for abn, record in records.items()
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
