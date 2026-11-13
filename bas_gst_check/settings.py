"""Read my-settings.toml. Empty values mean 'use the built-in default'."""

from __future__ import annotations

import os
import re
import tomllib
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from bas_gst_check.money import parse_money

HEX_COLOUR = re.compile(r"^#[0-9A-Fa-f]{6}$")
GUID_SHAPE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


@dataclass
class Settings:
    business_name: str = ""
    bas_period: str = "quarterly"
    gst_basis: str = "accrual"
    brand: str = "skip"
    abr_guid: str = ""
    abr_guid_rejected_shape: bool = False
    period_start: date | None = None
    period_end: date | None = None
    data_file: str = ""
    primary: str = ""
    accent: str = ""
    logo: str = ""
    tolerance: Decimal | None = None
    tax_invoice_threshold: Decimal | None = None
    capital_threshold: Decimal | None = None
    timezone: str = "Australia/Sydney"
    source: Path | None = None


def settings_path(start: Path | None = None) -> Path:
    return (start or Path.cwd()) / "my-settings.toml"


def guid_shape_ok(value: str) -> bool:
    return bool(GUID_SHAPE.fullmatch(value.strip()))


def save_abr_guid(path: Path, value: str) -> None:
    """Write the GUID only into my-settings.toml. Raises if the shape is wrong."""
    cleaned = value.strip().strip('"').strip("'")
    if not guid_shape_ok(cleaned):
        raise ValueError(
            "That does not look like an ABR GUID. It should be letters and numbers "
            "in the 8-4-4-4-12 shape. Nothing was saved."
        )
    if path.is_file():
        text = path.read_text(encoding="utf-8")
    else:
        example = Path(__file__).resolve().parents[1] / "my-settings.example.toml"
        text = example.read_text(encoding="utf-8") if example.is_file() else ""
    line = f'abr_guid = "{cleaned}"'
    if re.search(r"(?m)^abr_guid\s*=", text):
        text = re.sub(r"(?m)^abr_guid\s*=.*$", line, text, count=1)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += line + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_settings(path: Path | None = None) -> Settings:
    settings = Settings()
    file_path = path if path is not None else settings_path()
    if file_path.is_file():
        settings.source = file_path
        with file_path.open("rb") as handle:
            raw = tomllib.load(handle)
        _apply_file(settings, raw)
    env_guid = os.environ.get("ABR_GUID", "").strip()
    if env_guid:
        _set_guid(settings, env_guid)
    _validate(settings)
    return settings


def _apply_file(settings: Settings, raw: dict) -> None:
    settings.business_name = _text(raw.get("business_name"))
    if _text(raw.get("bas_period")):
        settings.bas_period = _text(raw.get("bas_period")).lower()
    if _text(raw.get("gst_basis")):
        settings.gst_basis = _text(raw.get("gst_basis")).lower()
    if _text(raw.get("brand")):
        settings.brand = _text(raw.get("brand")).lower()
    if _text(raw.get("abr_guid")):
        _set_guid(settings, _text(raw.get("abr_guid")))
    settings.period_start = _date(raw.get("period_start"))
    settings.period_end = _date(raw.get("period_end"))
    settings.data_file = _text(raw.get("data_file"))
    if _text(raw.get("timezone")):
        settings.timezone = _text(raw.get("timezone"))
    colours = raw.get("brand_colours") or {}
    settings.primary = _text(colours.get("primary"))
    settings.accent = _text(colours.get("accent"))
    settings.logo = _text(colours.get("logo"))
    thresholds = raw.get("thresholds") or {}
    settings.tolerance = _money(thresholds.get("gst_rounding_tolerance"))
    settings.tax_invoice_threshold = _money(thresholds.get("tax_invoice_threshold_inclusive"))
    settings.capital_threshold = _money(thresholds.get("capital_purchase_threshold"))


def _set_guid(settings: Settings, value: str) -> None:
    cleaned = value.strip()
    if guid_shape_ok(cleaned):
        settings.abr_guid = cleaned
        settings.abr_guid_rejected_shape = False
        return
    settings.abr_guid = ""
    settings.abr_guid_rejected_shape = True


def _validate(settings: Settings) -> None:
    if settings.bas_period not in {"quarterly", "monthly"}:
        raise ValueError("bas_period must be quarterly or monthly")
    if settings.gst_basis not in {"cash", "accrual"}:
        raise ValueError("gst_basis must be cash or accrual")
    if settings.brand not in {"skip", "preset", "custom"}:
        raise ValueError("brand must be skip, preset or custom")
    if settings.primary and not HEX_COLOUR.fullmatch(settings.primary):
        raise ValueError("brand primary colour must be a hex code such as #021A54")
    if settings.accent and not HEX_COLOUR.fullmatch(settings.accent):
        raise ValueError("brand accent colour must be a hex code such as #FF85BB")
    if (settings.period_start is None) != (settings.period_end is None):
        raise ValueError("set both period_start and period_end, or leave both blank")
    if (
        settings.period_start
        and settings.period_end
        and settings.period_start > settings.period_end
    ):
        raise ValueError("period_start is after period_end")
    try:
        ZoneInfo(settings.timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("timezone must be a name such as Australia/Sydney") from exc


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _date(value: object) -> date | None:
    text = _text(value)
    if not text:
        return None
    return date.fromisoformat(text)


def _money(value: object) -> Decimal | None:
    text = _text(value)
    if not text:
        return None
    return parse_money(text)
