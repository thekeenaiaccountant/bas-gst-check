from datetime import date
from decimal import Decimal

from bas_gst_check.rules import load_rules
from bas_gst_check.summarise import summarise
from tests.helpers import tx

RULES = load_rules()


def test_draft_labels_follow_the_file():
    transactions = [
        tx(side="sale", tax_code_label="GST on Income", net=Decimal("100.00"), gst=Decimal("10.00"), description="Design"),
        tx(side="sale", treatment="gst_free", tax_code_label="GST Free", net=Decimal("50.00"), gst=Decimal("0.00"), description="Export of posters"),
        tx(side="sale", treatment="input_taxed", tax_code_label="Input Taxed", net=Decimal("20.00"), gst=Decimal("0.00"), description="Interest received", account="Interest income"),
        tx(side="sale", treatment="bas_excluded", tax_code_label="BAS Excluded", net=Decimal("999.00"), gst=Decimal("0.00"), description="Owner drawing"),
        tx(net=Decimal("40.00"), gst=Decimal("4.00"), description="Stationery"),
        tx(description="Laptop", account="Computer equipment", net=Decimal("1000.00"), gst=Decimal("100.00"), force_capital=False),
        tx(treatment="bas_excluded", tax_code_label="BAS Excluded", gst=Decimal("0.00"), net=Decimal("500.00"), description="Fortnightly wages", account="Wages"),
        tx(side="unknown", treatment="unknown", tax_code_label="?", description="Mystery"),
    ]
    # The wages line matches usually-no-gst but that does not change the totals.
    summary = summarise(transactions, RULES)
    assert summary.g1 == Decimal("180.00")
    assert summary.gst_on_sales == Decimal("10.00")
    assert summary.gst_on_purchases == Decimal("104.00")
    assert summary.net == Decimal("-94.00")
    assert summary.position == "refundable"
    assert summary.g10 == Decimal("1100.00")
    assert summary.g11 == Decimal("44.00")
    assert summary.left_out == 1


def test_credit_note_reduces_sales_and_gst():
    summary = summarise(
        [tx(side="sale", tax_code_label="GST on Income", net=Decimal("-200.00"), gst=Decimal("-20.00"), description="Credit")],
        RULES,
    )
    assert summary.g1 == Decimal("-220.00")
    assert summary.gst_on_sales == Decimal("-20.00")
    assert summary.position == "refundable"


def test_rules_use_the_ato_thresholds():
    assert RULES.tax_invoice_threshold == Decimal("82.50")
    assert RULES.capital_threshold == Decimal("1000.00")
    assert RULES.tolerance == Decimal("0.05")
    assert date(2026, 7, 1).isoformat() == "2026-07-01"
