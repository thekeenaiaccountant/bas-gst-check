from datetime import date
from decimal import Decimal

from bas_gst_check.abr import AbrOutcome, SupplierLine
from bas_gst_check.checks import run_checks
from bas_gst_check.models import Comparison, Flag, Period, Summary
from bas_gst_check.report import PRESET, render_html, section_heading, supplier_sections
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
    assert 'class="disclaimer"' not in html
    assert 'class="stamp"' not in html
    assert '<details class="fold other">' in html


def test_supplier_rows_group_by_abn_and_gst_status():
    registered = tx(contact="Sable Commercial", supplier_abn="99000000000")
    cancelled = tx(
        contact="Bluegum Hosting",
        supplier_abn="99000000032",
        net=Decimal("140.00"),
        gst=Decimal("14.00"),
        description="Site hosting",
    )
    missing = tx(contact="Cinder Repairs", supplier_abn="", description="Door repair")
    abr = AbrOutcome(
        mode="on",
        message="checked",
        flags=[],
        notes=[],
        lines=[
            SupplierLine("99000000000", registered.date, "Sable Commercial", registered, "sable.pdf", "gst_registered"),
            SupplierLine("99000000032", cancelled.date, "Bluegum Hosting", cancelled, "bluegum.pdf", "cancelled"),
        ],
    )
    no_abn = Flag(
        code="bill_no_abn",
        title="No ABN was found on this bill",
        severity="error",
        why="No ABN was printed.",
        fix="Ask the supplier.",
        source_url="https://www.ato.gov.au/businesses-and-organisations/gst-excise-and-indirect-taxes/gst/tax-invoices",
        source_title="ATO",
        transaction=missing,
        supplier_name="Cinder Repairs",
    )
    problem, absent, good, checked = supplier_sections([no_abn], abr)
    assert checked is True
    assert [row.supplier for row in problem] == ["Bluegum Hosting"]
    assert "1B" in problem[0].action
    assert [row.supplier for row in absent] == ["Cinder Repairs"]
    assert absent[0].abn == "—"
    assert [row.supplier for row in good] == ["Sable Commercial"]
    assert section_heading("problem", 1, True) == "Not registered for GST, but GST was claimed (1)"
    assert section_heading("problem", 2, False) == "Couldn't check GST registration (2)"
    html = render_html(
        business="Fennel Street Workshop",
        period=Period(date(2026, 7, 1), date(2026, 9, 30)),
        basis="accrual",
        bas_period="quarterly",
        fictional=True,
        summary=Summary(
            g1=Decimal("0.00"),
            gst_on_sales=Decimal("0.00"),
            gst_on_purchases=Decimal("24.00"),
            net=Decimal("-24.00"),
            g10=Decimal("0.00"),
            g11=Decimal("264.00"),
            sales_counted=0,
            purchases_counted=2,
            left_out=0,
        ),
        flags=[no_abn],
        notes={},
        comparison=Comparison(has_previous=False),
        abr=abr,
        rules=load_rules(),
        logo_html="",
        brand_overrides={},
        period_warning="",
        theme="pooja",
    )
    assert "Not registered for GST, but GST was claimed (1)" in html
    assert "ABN not found (1)" in html
    assert "ABN found and GST registered (1)" in html
    assert '<details class="fold good">' in html
    assert '<details class="fold good" open' not in html
    assert '<details class="fold other" open' not in html
    assert 'class="stamp"' not in html
    assert "#DDF6E8" in html
    assert "#FDECEC" in html
    assert "#FFF0D6" in html
