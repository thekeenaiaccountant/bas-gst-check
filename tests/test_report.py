from datetime import date
from decimal import Decimal

from bas_gst_check.abr import AbrOutcome
from bas_gst_check.checks import run_checks
from bas_gst_check.models import Comparison, Period, Summary
from bas_gst_check.report import PRESET, render_html
from bas_gst_check.rules import load_rules
from tests.helpers import tx


def test_report_escapes_text_and_can_wear_the_preset():
    transaction = tx(contact="<script>", description="Copy paper")
    flags = run_checks([transaction], Period(date(2026, 7, 1), date(2026, 9, 30)), load_rules())
    summary = Summary(
        g1=Decimal("0.00"),
        gst_on_sales=Decimal("0.00"),
        gst_on_purchases=Decimal("10.00"),
        net=Decimal("-10.00"),
        g10=Decimal("0.00"),
        g11=Decimal("110.00"),
        sales_counted=0,
        purchases_counted=1,
        left_out=0,
    )
    html = render_html(
        business="Fennel Street Workshop",
        period=Period(date(2026, 7, 1), date(2026, 9, 30)),
        basis="accrual",
        bas_period="quarterly",
        fictional=True,
        summary=summary,
        flags=flags,
        notes={},
        comparison=Comparison(has_previous=False),
        abr=AbrOutcome(mode="off", message="Supplier ABN lookup is off.", flags=[], notes=[]),
        rules=load_rules(),
        logo_html="",
        brand_overrides=dict(PRESET),
        period_warning="",
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "#021A54" in html
    assert "#FF85BB" in html
    assert "Not tax advice" in html
    assert "Refundable" in html
