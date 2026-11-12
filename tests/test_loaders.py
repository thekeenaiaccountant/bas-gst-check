from pathlib import Path

from bas_gst_check.loaders import load_transactions
from bas_gst_check.rules import load_rules

RULES = load_rules()


def test_csv_headers_like_an_export(tmp_path: Path):
    path = tmp_path / "quarter.csv"
    path.write_text(
        "Date,Contact,Description,Account,Net Amount,GST Amount,Tax Code,Type\n"
        "15/07/2026,Brindle Archive,Identity system,Sales,800.00,80.00,GST on Income,sale\n",
        encoding="utf-8",
    )
    loaded = load_transactions(path, RULES)
    assert loaded.errors == []
    assert loaded.transactions[0].side == "sale"
    assert loaded.transactions[0].inclusive == loaded.transactions[0].net + loaded.transactions[0].gst


def test_a_bad_date_is_reported_and_not_silently_dropped(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text(
        '{"transactions":[{"date":"yesterday","type":"sale","contact":"Brindle Archive",'
        '"description":"Poster","account":"Sales","net_amount":"10.00","gst_amount":"1.00",'
        '"tax_code":"GST on Income"}]}',
        encoding="utf-8",
    )
    loaded = load_transactions(path, RULES)
    assert loaded.transactions == []
    assert loaded.errors
    assert "yesterday" in loaded.errors[0]


def test_empty_file(tmp_path: Path):
    path = tmp_path / "empty.json"
    path.write_text("[]", encoding="utf-8")
    loaded = load_transactions(path, RULES)
    assert loaded.errors
