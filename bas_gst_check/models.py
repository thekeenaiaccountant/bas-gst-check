"""Transactions, flags and the draft BAS summary."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal

Side = Literal["sale", "purchase", "unknown"]
Treatment = Literal["taxable", "gst_free", "bas_excluded", "input_taxed", "unknown"]
Severity = Literal["error", "review"]


@dataclass(frozen=True)
class Transaction:
    row: int
    date: date
    side: Side
    treatment: Treatment
    tax_code_label: str
    contact: str
    description: str
    account: str
    net: Decimal
    gst: Decimal
    supplier_abn: str
    reference: str
    force_capital: bool
    code_conflicts_with_side: bool

    @property
    def inclusive(self) -> Decimal:
        return self.net + self.gst


@dataclass(frozen=True)
class Period:
    start: date
    end: date
    inferred: bool = False


@dataclass
class Summary:
    g1: Decimal
    gst_on_sales: Decimal
    gst_on_purchases: Decimal
    net: Decimal
    g10: Decimal
    g11: Decimal
    sales_counted: int
    purchases_counted: int
    left_out: int

    @property
    def position(self) -> Literal["payable", "refundable", "nil"]:
        if self.net > 0:
            return "payable"
        if self.net < 0:
            return "refundable"
        return "nil"


@dataclass
class Flag:
    code: str
    title: str
    severity: Severity
    why: str
    fix: str
    source_url: str
    source_title: str
    transaction: Transaction | None = None
    detail_key: str = ""
    fingerprint: str = ""
    short_id: str = ""
    supplier_name: str = ""
    line_date: date | None = None
    line_amount: Decimal | None = None
    line_gst: Decimal | None = None
    line_abn: str = ""


@dataclass
class AbrNote:
    """A lookup that did not finish. It is not a GST finding."""

    supplier_abn: str
    contact: str
    reason: str


@dataclass
class Comparison:
    has_previous: bool
    previous_at: str = ""
    deltas: dict[str, Decimal] = field(default_factory=dict)
    new_flags: list[Flag] = field(default_factory=list)
    cleared_labels: list[str] = field(default_factory=list)
    still_open: int = 0


@dataclass
class Note:
    status: Literal["fixed", "ignored"]
    text: str
    updated: str
    label: str = ""
