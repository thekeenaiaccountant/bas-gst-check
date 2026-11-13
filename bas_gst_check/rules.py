"""Load thresholds and keyword hints from config/rules.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from bas_gst_check.money import parse_money


@dataclass(frozen=True)
class NoGstGroup:
    id: str
    title: str
    why: str
    source: str
    phrases: tuple[str, ...]


@dataclass(frozen=True)
class CodeSuggestion:
    id: str
    suggest: str
    note: str
    phrases: tuple[str, ...]


@dataclass(frozen=True)
class Rules:
    tolerance: Decimal
    tax_invoice_threshold: Decimal
    capital_threshold: Decimal
    abr_timeout_seconds: float
    bill_date_tolerance_days: int
    supplier_jump_percent: Decimal
    supplier_jump_floor: Decimal
    no_gst_groups: tuple[NoGstGroup, ...]
    code_suggestions: tuple[CodeSuggestion, ...]
    usually_taxable_phrases: tuple[str, ...]
    capital_item_phrases: tuple[str, ...]
    not_capital_phrases: tuple[str, ...]
    capital_account_phrases: tuple[str, ...]
    sale_account_phrases: tuple[str, ...]
    purchase_account_phrases: tuple[str, ...]
    personal_phrases: tuple[str, ...]


def rules_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "rules.toml"


def load_rules(path: Path | None = None) -> Rules:
    source = path or rules_path()
    with source.open("rb") as handle:
        raw = tomllib.load(handle)
    thresholds = raw["thresholds"]
    groups = tuple(
        NoGstGroup(
            id=item["id"],
            title=item["title"],
            why=item["why"],
            source=item["source"],
            phrases=tuple(item["phrases"]),
        )
        for item in raw["no_gst_groups"]
    )
    lists = raw["lists"]
    suggestions = tuple(
        CodeSuggestion(
            id=item["id"],
            suggest=item["suggest"],
            note=item["note"],
            phrases=tuple(item["phrases"]),
        )
        for item in raw.get("code_suggestions") or []
    )
    return Rules(
        tolerance=parse_money(thresholds["gst_rounding_tolerance"]),
        tax_invoice_threshold=parse_money(thresholds["tax_invoice_threshold_inclusive"]),
        capital_threshold=parse_money(thresholds["capital_purchase_threshold"]),
        abr_timeout_seconds=float(thresholds["abr_timeout_seconds"]),
        bill_date_tolerance_days=int(thresholds.get("bill_date_tolerance_days") or 3),
        supplier_jump_percent=parse_money(str(thresholds.get("supplier_jump_percent") or "50")),
        supplier_jump_floor=parse_money(str(thresholds.get("supplier_jump_floor") or "200")),
        no_gst_groups=groups,
        code_suggestions=suggestions,
        usually_taxable_phrases=tuple(lists["usually_taxable_phrases"]),
        capital_item_phrases=tuple(lists["capital_item_phrases"]),
        not_capital_phrases=tuple(lists["not_capital_phrases"]),
        capital_account_phrases=tuple(lists["capital_account_phrases"]),
        sale_account_phrases=tuple(lists["sale_account_phrases"]),
        purchase_account_phrases=tuple(lists["purchase_account_phrases"]),
        personal_phrases=tuple(lists.get("personal_phrases") or []),
    )
