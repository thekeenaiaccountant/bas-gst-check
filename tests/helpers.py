"""Shared builders for the tests. Amounts are Decimal strings."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from bas_gst_check.models import Transaction


def tx(**overrides: object) -> Transaction:
    values: dict[str, object] = {
        "row": 1,
        "date": date(2026, 7, 15),
        "side": "purchase",
        "treatment": "taxable",
        "tax_code_label": "GST on Expenses",
        "contact": "Lumen Stationery",
        "description": "Copy paper",
        "account": "Office expenses",
        "net": Decimal("100.00"),
        "gst": Decimal("10.00"),
        "supplier_abn": "11111111111",
        "reference": "INV-1",
        "force_capital": False,
        "code_conflicts_with_side": False,
    }
    values.update(overrides)
    return Transaction(**values)  # type: ignore[arg-type]
