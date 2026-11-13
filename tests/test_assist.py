"""Bill match, code suggestions, personal spend, supplier changes, and the explainer."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from bas_gst_check.billmatch import compare_bills
from bas_gst_check.billread import BillReading
from bas_gst_check.explain import explain_bas
from bas_gst_check.models import Summary
from bas_gst_check.rules import load_rules
from bas_gst_check.suggestions import suggest_flags
from bas_gst_check.suppliers import purchase_totals, supplier_flags
from tests.helpers import tx

RULES = load_rules()


def _reading(supplier: str, on: str, total: str, gst: str | None = None) -> BillReading:
    return BillReading(
        file_name=f"{supplier}.pdf",
        supplier=supplier,
        text="",
        unreadable=False,
        bill_date=date.fromisoformat(on),
        total=Decimal(total),
        gst=Decimal(gst) if gst is not None else None,
    )


def test_a_bill_matches_a_close_date_and_a_fuzzy_name():
    purchase = tx(contact="Sable Commercial", date=date(2026, 7, 1), net=Decimal("2200"), gst=Decimal("220"))
    near = _reading("Sable Commercial Pty Ltd", "2026-07-03", "2420.00", "220.00")
    far = _reading("Sable Commercial", "2026-07-20", "2420.00", "220.00")
    flags = compare_bills([near, far], [purchase], RULES)
    assert not any(flag.code == "gst_without_bill" for flag in flags)
    assert any(flag.code == "bill_unmatched" for flag in flags) is False
    assert {flag.code for flag in flags} == set()


def test_gst_on_the_bill_is_compared_with_the_file():
    purchase = tx(contact="Kindling Software", net=Decimal("150.00"), gst=Decimal("15.00"), description="Plugin licence")
    reading = _reading("Kindling Software", "2026-07-15", "165.00", "20.00")
    flags = compare_bills([reading], [purchase], RULES)
    assert [flag.code for flag in flags] == ["gst_on_bill"]
    assert "20.00" in flags[0].why
    assert "15.00" in flags[0].why


def test_gst_claimed_without_a_bill_and_a_bill_without_a_line():
    claimed = tx(contact="Parcel Counter", description="Large crate delivery", net=Decimal("180"), gst=Decimal("18"))
    orphan = _reading("Nobody Trading", "2026-07-20", "999.00", "90.82")
    flags = compare_bills([orphan], [claimed], RULES)
    assert {flag.code for flag in flags} == {"gst_without_bill"}


def test_code_suggestions_and_personal_wording_stay_suggestions():
    insurance = tx(
        contact="Nettle Insurance",
        description="Insurance premium",
        account="Insurance",
        treatment="gst_free",
        tax_code_label="GST Free",
        gst=Decimal("0.00"),
        net=Decimal("180.00"),
    )
    duty = tx(
        contact="Companies Register",
        description="Stamp duty on the lease",
        account="Filing fees",
        net=Decimal("90.00"),
        gst=Decimal("9.00"),
    )
    streaming = tx(contact="Riverbend Bank", description="Netflix subscription", account="Staff amenities")
    bank = tx(contact="Riverbend Bank", description="Account keeping fee", account="Bank fees", gst=Decimal("2.20"), net=Decimal("22"))
    flags = suggest_flags([insurance, duty, streaming, bank], RULES, {"codes": [], "personal": []})
    codes = {flag.code for flag in flags}
    assert "suggested_code" in codes
    assert "personal_spend" in codes
    assert any(flag.transaction and flag.transaction.description == "Account keeping fee" and flag.code == "suggested_code" for flag in flags) is False
    assert any("Suggestion, check it" in flag.fix for flag in flags)
    assert any(flag.fix.startswith("May be personal, check") for flag in flags)
    ai = suggest_flags(
        [tx(description="Pouch restock", treatment="gst_free", tax_code_label="GST Free", gst=Decimal("0"), net=Decimal("40"), account="Office expenses")],
        RULES,
        {"codes": [{"description": "Pouch restock", "suggest": "GST on Expenses", "why": "A pouch is usually taxable."}], "personal": []},
    )
    assert ai[0].code == "suggested_code"
    assert "Suggestion, check it" in ai[0].fix


def test_new_and_jumped_suppliers_use_the_floor(tmp_path: Path):
    current = [
        tx(contact="Bluegum Hosting", net=Decimal("140"), gst=Decimal("14"), description="Site hosting"),
        tx(contact="Loom Advertising", net=Decimal("800"), gst=Decimal("80"), description="Magazine listing"),
        tx(contact="Sable Commercial", net=Decimal("200"), gst=Decimal("20"), description="Studio rent"),
        tx(contact="Tiny News", net=Decimal("10"), gst=Decimal("1"), description="Clipping"),
    ]
    previous = {
        "Loom Advertising": Decimal("200.00"),
        "Sable Commercial": Decimal("220.00"),
        "Tiny News": Decimal("4.00"),
    }
    flags = supplier_flags(current, previous, RULES)
    found = {flag.code: flag for flag in flags}
    assert "supplier_new" in found
    assert found["supplier_new"].transaction.contact == "Bluegum Hosting"
    assert "supplier_jump" in found
    assert found["supplier_jump"].transaction.contact == "Loom Advertising"
    assert "Tiny News" not in {flag.transaction.contact for flag in flags}
    assert supplier_flags(current, None, RULES) == []
    assert purchase_totals(current)["Bluegum Hosting"] == Decimal("154.00")


def test_explainer_uses_the_numbers_and_does_not_give_advice():
    summary = Summary(
        g1=Decimal("100.00"),
        gst_on_sales=Decimal("10.00"),
        gst_on_purchases=Decimal("30.00"),
        net=Decimal("-20.00"),
        g10=Decimal("0"),
        g11=Decimal("330"),
        sales_counted=1,
        purchases_counted=1,
        left_out=0,
    )
    text = explain_bas(
        summary,
        {"Loom Advertising": Decimal("800")},
        {"Loom Advertising": Decimal("200")},
        {"Advertising": Decimal("900")},
        {"Advertising": Decimal("200")},
    )
    assert "Draft net GST is $20.00 refundable" in text
    assert "1B is $20.00 higher than 1A" in text
    assert "Loom Advertising" in text
    assert "up $600.00" in text
    assert "Advertising" in text
    assert "up $700.00" in text
    lowered = text.lower()
    assert "you should" not in lowered
    assert "recommend" not in lowered
    assert "advice" not in lowered
    plain = explain_bas(summary, {}, None, {}, None)
    assert "previous quarter" not in plain
