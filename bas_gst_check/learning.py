"""Local memory of hard bills and ABNs the user confirmed. Gitignored under .local."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from bas_gst_check.abn import abn_is_valid, digits_only
from bas_gst_check.billread import HardNote


def learning_path(state_dir: Path) -> Path:
    return state_dir / "abn-learning.json"


def load_learning(path: Path) -> dict:
    if not path.is_file():
        return {"hard": [], "confirmed": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"hard": [], "confirmed": {}}
    if not isinstance(raw, dict):
        return {"hard": [], "confirmed": {}}
    hard = raw.get("hard") if isinstance(raw.get("hard"), list) else []
    confirmed = raw.get("confirmed") if isinstance(raw.get("confirmed"), dict) else {}
    return {"hard": hard, "confirmed": confirmed}


def save_learning(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "hard": data.get("hard") or [],
        "confirmed": data.get("confirmed") or {},
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def confirmed_abns(data: dict) -> dict[str, str]:
    found: dict[str, str] = {}
    for key, item in (data.get("confirmed") or {}).items():
        if isinstance(item, dict) and abn_is_valid(str(item.get("abn") or "")):
            found[str(key)] = digits_only(str(item["abn"]))
    return found


def hints(data: dict) -> dict[str, str]:
    found: dict[str, str] = {}
    for key, item in (data.get("confirmed") or {}).items():
        if isinstance(item, dict) and str(item.get("hint") or "").strip():
            found[str(key)] = str(item["hint"]).strip()
    return found


def remember_hard(data: dict, notes: list[HardNote]) -> list[str]:
    """Append this run's hard bills. Return short lines for the report."""
    lines: list[str] = []
    for note in notes:
        data.setdefault("hard", []).append({
            "supplier": note.supplier,
            "file": note.file_name,
            "reason": note.reason,
            "detail": note.detail,
            "at": _now(),
        })
        lines.append(f"{note.file_name} ({note.supplier}): {note.detail}")
    return lines


def earlier_lines(data: dict, this_run_files: set[str], limit: int = 6) -> list[str]:
    lines: list[str] = []
    for item in reversed(data.get("hard") or []):
        if not isinstance(item, dict):
            continue
        if item.get("file") in this_run_files:
            continue
        hint = item.get("detail") or item.get("reason") or "This bill was hard to read."
        lines.append(f"Earlier, {item.get('file') or 'a bill'} ({item.get('supplier') or 'unnamed'}): {hint}")
        if len(lines) >= limit:
            break
    return lines


def confirm_supplier(path: Path, supplier: str, abn: str, hint: str = "") -> str:
    digits = digits_only(abn)
    if not abn_is_valid(digits):
        return "That number is not a valid ABN. It fails the official checksum, so it was not saved."
    data = load_learning(path)
    key = " ".join(supplier.casefold().split())
    data.setdefault("confirmed", {})[key] = {
        "abn": digits,
        "hint": hint.strip(),
        "at": _now(),
    }
    save_learning(path, data)
    extra = f" Next time, look here first: {hint.strip()}." if hint.strip() else ""
    return f"Saved the ABN you confirmed for {supplier}. The digits passed the checksum.{extra}"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
