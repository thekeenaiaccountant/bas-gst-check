from datetime import date
from decimal import Decimal

from bas_gst_check.checks import run_checks
from bas_gst_check.models import Period
from bas_gst_check.rules import load_rules
from tests.helpers import tx

PERIOD = Period(date(2026, 7, 1), date(2026, 9, 30))
RULES = load_rules()


def codes(transactions):
    return {flag.code for flag in run_checks(transactions, PERIOD, RULES)}


def test_clean_taxable_purchase_is_only_a_tax_invoice_reminder():
    found = codes([tx()])
    assert found == {"tax_invoice"}


def test_gst_must_be_one_eleventh():
    bad = tx(net=Decimal("2000.00"), gst=Decimal("100.00"), side="sale", tax_code_label="GST on Income")
    near = tx(net=Decimal("100.00"), gst=Decimal("10.05"))
    assert "gst_amount" in codes([bad])
    assert "gst_amount" not in codes([near])


def test_gst_on_a_free_code_without_a_keyword():
    found = codes([
        tx(treatment="gst_free", tax_code_label="GST Free", gst=Decimal("5.00"), description="Window cleaning"),
    ])
    assert "gst_amount" in found


def test_each_usually_untaxed_group():
    samples = [
        ("Account keeping fee", "Bank fees"),
        ("Interest received", "Interest income"),
        ("Fortnightly wages", "Wages"),
        ("Superannuation contribution", "Superannuation"),
        ("ASIC annual review fee", "Filing fees"),
        ("Plain milk and bread", "Staff amenities"),
    ]
    for description, account in samples:
        found = codes([tx(description=description, account=account)])
        assert "usually_no_gst" in found, description
        assert "tax_invoice" not in found


def test_correct_no_gst_lines_stay_quiet():
    quiet = [
        tx(treatment="input_taxed", tax_code_label="Input Taxed", gst=Decimal("0.00"), description="Account keeping fee", account="Bank fees", net=Decimal("15.00")),
        tx(treatment="bas_excluded", tax_code_label="BAS Excluded", gst=Decimal("0.00"), description="Fortnightly wages", account="Wages", net=Decimal("3200.00")),
        tx(treatment="gst_free", tax_code_label="GST Free", gst=Decimal("0.00"), description="Plain flour and white rice", account="Staff amenities", net=Decimal("36.00")),
    ]
    assert codes(quiet) == set()


def test_missing_gst_and_bas_excluded():
    missing = tx(treatment="gst_free", tax_code_label="GST Free", gst=Decimal("0.00"), net=Decimal("90.00"), description="Design software subscription", account="Software")
    excluded = tx(treatment="bas_excluded", tax_code_label="BAS Excluded", gst=Decimal("0.00"), net=Decimal("250.00"), description="Online ads", account="Advertising")
    assert "missing_gst" in codes([missing])
    assert "bas_excluded_taxable" in codes([excluded])


def test_outside_period_and_duplicate_and_capital_and_missing_abn():
    outside = tx(date=date(2026, 6, 18))
    first = tx(description="Copy paper", net=Decimal("50.00"), gst=Decimal("5.00"), row=1)
    second = tx(description="Copy paper", net=Decimal("50.00"), gst=Decimal("5.00"), row=2)
    camera = tx(description="Studio camera", account="General expenses", net=Decimal("1600.00"), gst=Decimal("160.00"))
    laptop = tx(description="Laptop for the studio", account="Computer equipment", net=Decimal("1800.00"), gst=Decimal("180.00"))
    missing = tx(supplier_abn="", net=Decimal("180.00"), gst=Decimal("18.00"), description="Large crate delivery")
    exact = tx(net=Decimal("75.00"), gst=Decimal("7.50"), description="Copy paper")
    assert "outside_period" in codes([outside])
    assert "duplicate" in codes([first, second])
    assert "capital_split" in codes([camera])
    assert "capital_split" not in codes([laptop])
    assert "missing_abn" in codes([missing])
    assert "tax_invoice" not in codes([exact])


def test_unknown_side_code_and_conflict_are_left_for_a_human():
    unknown_side = tx(side="unknown", treatment="gst_free", tax_code_label="GST Free", gst=Decimal("0.00"))
    unknown_code = tx(treatment="unknown", tax_code_label="Something else")
    conflict = tx(side="purchase", tax_code_label="GST on Income", code_conflicts_with_side=True)
    found = codes([unknown_side, unknown_code, conflict])
    assert {"unknown_side", "unknown_tax_code", "side_mismatch"} <= found
