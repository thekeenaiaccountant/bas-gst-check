from datetime import date
from decimal import Decimal
from pathlib import Path

from bas_gst_check.checks import run_checks
from bas_gst_check.engine import execute
from bas_gst_check.models import Period
from bas_gst_check.loaders import load_transactions
from bas_gst_check.review_log import assign_ids
from bas_gst_check.rules import load_rules
from bas_gst_check.settings import Settings
from tests.helpers import tx

RULES = load_rules()
EXPORTS = Path("examples/exports")


def test_xero_myob_and_quickbooks_samples_are_recognised():
    xero = load_transactions(EXPORTS / "xero-account-transactions.csv", RULES)
    myob = load_transactions(EXPORTS / "myob-purchases.csv", RULES)
    quickbooks = load_transactions(EXPORTS / "quickbooks-gst.csv", RULES)
    assert xero.errors == []
    assert myob.errors == []
    assert quickbooks.errors == []
    xero_codes = {item.tax_code_label: item.treatment for item in xero.transactions}
    assert xero_codes["GST on Income"] == "taxable"
    assert xero.transactions[0].side == "sale"
    assert xero.transactions[1].side == "purchase"
    myob_by_code = {item.tax_code_label: item for item in myob.transactions}
    assert myob_by_code["GST"].treatment == "taxable"
    assert myob_by_code["GST"].side == "purchase"
    assert myob_by_code["FRE"].treatment == "gst_free"
    assert myob_by_code["EXP"].side == "sale"
    assert myob_by_code["INP"].treatment == "input_taxed"
    assert myob_by_code["N-T"].treatment == "bas_excluded"
    assert myob_by_code["CAP"].force_capital is True
    assert quickbooks.transactions[0].side == "sale"
    assert quickbooks.transactions[0].treatment == "taxable"
    assert quickbooks.transactions[2].treatment == "gst_free"
    assert quickbooks.transactions[3].treatment == "bas_excluded"


def test_excel_round_trip_and_unknown_code_is_not_a_nil_bas(tmp_path: Path):
    sheet_path = EXPORTS / "quickbooks-gst.xlsx"
    loaded = load_transactions(sheet_path, RULES)
    csv_loaded = load_transactions(EXPORTS / "quickbooks-gst.csv", RULES)
    assert loaded.errors == []
    assert len(loaded.transactions) == len(csv_loaded.transactions)
    mystery = tmp_path / "mystery.csv"
    mystery.write_text(
        "Date,Transaction type,Name,Memo,Account,Amount,Tax amount,Tax code\n"
        "2026-07-03,Invoice,Plover Shire Hall,Wayfinding concept,Sales,1000.00,100.00,WIDGET\n",
        encoding="utf-8",
    )
    odd = load_transactions(mystery, RULES)
    assert odd.errors == []
    assert odd.transactions[0].treatment == "unknown"
    result = execute(
        mystery,
        settings=Settings(period_start=date(2026, 7, 1), period_end=date(2026, 9, 30)),
        output_dir=tmp_path / "out",
        state_dir=tmp_path / "state",
        bills_dir=tmp_path / "no-bills",
    )
    html = (tmp_path / "out" / "bas-gst-check.html").read_text(encoding="utf-8")
    assert "not a nil BAS" in html
    assert "Not a usable BAS" in html
    assert result.summary is not None
    assert result.summary.g1 == 0


def test_a_real_file_without_a_period_is_not_guessed(tmp_path: Path):
    path = tmp_path / "quarter.csv"
    path.write_text(
        "Date,Contact,Description,Account,Net,GST,Tax Code,Type\n"
        "2026-07-03,Plover Shire Hall,Wayfinding concept,Sales,1000.00,100.00,GST on Income,sale\n",
        encoding="utf-8",
    )
    result = execute(path, settings=Settings(), output_dir=tmp_path / "out", state_dir=tmp_path / "state")
    assert result.summary is None
    html = (tmp_path / "out" / "bas-gst-check.html").read_text(encoding="utf-8")
    assert "could not be checked" in html
    assert "Which quarter" in html


def test_a_bad_file_still_writes_a_report(tmp_path: Path):
    path = tmp_path / "empty.json"
    path.write_text("[]", encoding="utf-8")
    result = execute(path, settings=Settings(), output_dir=tmp_path / "out", state_dir=tmp_path / "state")
    assert result.html_path is not None
    assert result.html_path.is_file()
    assert "could not be checked" in result.html_path.read_text(encoding="utf-8")


def test_flag_numbers_stay_put_when_a_new_line_appears():
    period = Period(date(2026, 7, 1), date(2026, 9, 30))
    first = tx(description="Brand workshop", net=Decimal("2000.00"), gst=Decimal("100.00"), side="sale", tax_code_label="GST on Income")
    second = tx(date=date(2026, 6, 18), description="June leftover invoice", side="sale", tax_code_label="GST on Income")
    original = run_checks([first], period, RULES)
    remembered = assign_ids(original, {})
    kept = original[0].short_id
    again = run_checks([second, first], period, RULES)
    assign_ids(again, remembered)
    matched = next(flag for flag in again if flag.transaction and flag.transaction.description == "Brand workshop")
    assert matched.short_id == kept
    fresh = next(flag for flag in again if flag.transaction and flag.transaction.description == "June leftover invoice")
    assert fresh.short_id != kept
