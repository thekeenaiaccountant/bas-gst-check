"""Local notes and the previous run. Stored under .local, which is gitignored."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from bas_gst_check.checks import CHECK_ORDER
from bas_gst_check.models import Comparison, Flag, Note, Summary

SUMMARY_KEYS = ("g1", "gst_on_sales", "gst_on_purchases", "net", "g10", "g11")


def fingerprint(flag: Flag) -> str:
    transaction = flag.transaction
    parts = [
        flag.code,
        flag.detail_key,
        transaction.date.isoformat() if transaction else "",
        transaction.contact if transaction else "",
        transaction.description if transaction else "",
        str(transaction.net) if transaction else "",
        str(transaction.gst) if transaction else "",
        transaction.supplier_abn if transaction else "",
    ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]


def assign_ids(flags: list[Flag]) -> None:
    for flag in flags:
        flag.fingerprint = fingerprint(flag)
    order = {code: index for index, code in enumerate(CHECK_ORDER)}
    flags.sort(key=lambda flag: (
        0 if flag.severity == "error" else 1,
        order.get(flag.code, 99),
        flag.transaction.date.isoformat() if flag.transaction else "",
        flag.transaction.contact if flag.transaction else "",
        flag.detail_key,
        flag.fingerprint,
    ))
    for index, flag in enumerate(flags, start=1):
        flag.short_id = f"F-{index:02d}"


def load_notes(path: Path) -> dict[str, Note]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    notes: dict[str, Note] = {}
    items = raw.get("items") if isinstance(raw, dict) else None
    if not isinstance(items, dict):
        return notes
    for key, item in items.items():
        if not isinstance(item, dict):
            continue
        status = item.get("status")
        if status not in {"fixed", "ignored"}:
            continue
        notes[str(key)] = Note(
            status=status,
            text=str(item.get("text") or ""),
            updated=str(item.get("updated") or ""),
            label=str(item.get("label") or ""),
        )
    return notes


def save_notes(path: Path, notes: dict[str, Note]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "items": {
            key: {
                "status": note.status,
                "text": note.text,
                "updated": note.updated,
                "label": note.label,
            }
            for key, note in notes.items()
        }
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def set_note(path: Path, fingerprint_id: str, status: str, text: str, label: str) -> None:
    notes = load_notes(path)
    if status == "open":
        notes.pop(fingerprint_id, None)
    elif status in {"fixed", "ignored"}:
        notes[fingerprint_id] = Note(
            status=status,
            text=text.strip(),
            updated=_now(),
            label=label,
        )
    else:
        raise ValueError("status must be fixed, ignored or open")
    save_notes(path, notes)


def load_previous(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict) or "flags" not in raw:
        return None
    return raw


def save_previous(path: Path, summary: Summary, flags: list[Flag], period_start: str, period_end: str, business: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ran_at": _now(),
        "business_name": business,
        "period_start": period_start,
        "period_end": period_end,
        "summary": {key: str(getattr(summary, key)) for key in SUMMARY_KEYS},
        "flags": [
            {
                "id": flag.short_id,
                "fingerprint": flag.fingerprint,
                "code": flag.code,
                "label": _label(flag),
            }
            for flag in flags
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def compare(previous: dict | None, summary: Summary, flags: list[Flag]) -> Comparison:
    if not previous:
        return Comparison(has_previous=False, still_open=len(flags))
    old_summary = previous.get("summary") or {}
    deltas: dict[str, Decimal] = {}
    for key in SUMMARY_KEYS:
        old = Decimal(str(old_summary.get(key) or "0"))
        deltas[key] = getattr(summary, key) - old
    old_flags = previous.get("flags") or []
    old_by_id = {item.get("fingerprint"): item for item in old_flags if isinstance(item, dict)}
    current_ids = {flag.fingerprint for flag in flags}
    new_flags = [flag for flag in flags if flag.fingerprint not in old_by_id]
    cleared = [
        str(item.get("label") or item.get("code") or "a previous flag")
        for key, item in old_by_id.items()
        if key not in current_ids
    ]
    return Comparison(
        has_previous=True,
        previous_at=str(previous.get("ran_at") or ""),
        deltas=deltas,
        new_flags=new_flags,
        cleared_labels=cleared,
        still_open=sum(1 for flag in flags if flag.fingerprint in old_by_id),
    )


def _label(flag: Flag) -> str:
    transaction = flag.transaction
    if transaction is None:
        return flag.title
    return f"{flag.short_id} {transaction.date.isoformat()} {transaction.contact} — {transaction.description}"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
