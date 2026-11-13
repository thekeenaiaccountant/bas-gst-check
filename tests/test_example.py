import json
import re
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from bas_gst_check.abn import abn_is_valid
from bas_gst_check.engine import execute
from bas_gst_check.loaders import load_transactions
from bas_gst_check.review_log import set_note
from bas_gst_check.rules import load_rules
from bas_gst_check.settings import Settings
from tests.test_abr import FIXTURES, guid

EXAMPLE = Path("examples/fennel-street-workshop.json")
EXPECTED = {
    "gst_amount",
    "usually_no_gst",
    "missing_gst",
    "bas_excluded_taxable",
    "duplicate",
    "outside_period",
    "capital_split",
    "tax_invoice",
    "bill_unreadable",
    "bill_no_abn",
    "bill_bad_checksum",
    "bill_several_abns",
    "bill_unmatched",
    "gst_on_bill",
    "gst_without_bill",
    "suggested_code",
    "personal_spend",
    "supplier_new",
    "supplier_jump",
    "abn_not_found",
    "abn_cancelled",
    "abn_not_gst_registered",
}


def _section_count(page: str, label: str) -> int:
    match = re.search(re.escape(label) + r" \((\d+)\)", page)
    assert match, label
    return int(match.group(1))


def fetch(url: str, timeout: float) -> str:
    abn = parse_qs(urlparse(url).query)["abn"][0]
    return FIXTURES[abn]


def test_example_is_fiction_and_covers_every_check(tmp_path: Path):
    raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    assert raw["fictional"] is True
    assert 60 <= len(raw["transactions"]) <= 80
    for row in raw["transactions"]:
        abn = row.get("supplier_abn") or ""
        if abn:
            assert not abn_is_valid(abn)
    def blocked(url: str, timeout: float) -> str:
        raise AssertionError("example run without a GUID must not call the ABR")

    plain = execute(
        EXAMPLE,
        settings=Settings(),
        output_dir=tmp_path / "plain",
        state_dir=tmp_path / "plain-state",
        fetch=blocked,
    )
    assert plain.errors == []
    assert plain.abr_mode == "off"
    assert not any(flag.code.startswith("abn_") for flag in plain.flags)
    plain_html = (tmp_path / "plain" / "bas-gst-check.html").read_text(encoding="utf-8")
    assert "ABN check is off" in plain_html
    assert "set up ABN check" in plain_html
    assert "Couldn't check GST registration" in plain_html
    assert "Not registered for GST, but GST was claimed" not in plain_html
    assert _section_count(plain_html, "ABN not found") >= 1

    checked = execute(
        EXAMPLE,
        settings=Settings(abr_guid=guid()),
        output_dir=tmp_path / "checked",
        state_dir=tmp_path / "checked-state",
        fetch=fetch,
    )
    found = {flag.code for flag in checked.flags}
    assert found == EXPECTED
    assert checked.summary is not None
    assert checked.summary.net == checked.summary.gst_on_sales - checked.summary.gst_on_purchases
    html = (tmp_path / "checked" / "bas-gst-check.html").read_text(encoding="utf-8")
    assert "Not tax advice" in html
    assert "Fennel Street Workshop" in html
    assert "made-up example" in html
    assert guid() not in html
    assert "checksum" in html
    assert _section_count(html, "Not registered for GST, but GST was claimed") >= 1
    assert _section_count(html, "ABN not found") >= 1
    assert _section_count(html, "ABN found and GST registered") >= 1
    assert _section_count(html, "Bills vs Xero") >= 1
    assert "Suggestion, check it" in html
    assert "May be personal, check" in html
    assert "Draft net GST is" in html
    assert '<details class="fold good">' in html
    assert '<details class="fold other">' in html
    assert 'class="stamp"' not in html
    assert 'class="disclaimer"' not in html
    csv_text = (tmp_path / "checked" / "flagged-items.csv").read_text(encoding="utf-8")
    assert "flag_id" in csv_text
    assert guid() not in csv_text


def test_csv_matches_the_json_totals():
    rules = load_rules()
    json_loaded = load_transactions(EXAMPLE, rules)
    csv_loaded = load_transactions(Path("examples/fennel-street-workshop.csv"), rules)
    assert json_loaded.errors == []
    assert csv_loaded.errors == []
    assert len(json_loaded.transactions) == len(csv_loaded.transactions)
    json_net = sum((item.net for item in json_loaded.transactions), start=Decimal("0"))
    csv_net = sum((item.net for item in csv_loaded.transactions), start=Decimal("0"))
    assert json_net == csv_net


def test_a_note_comes_back_on_the_next_run(tmp_path: Path):
    state = tmp_path / "state"
    first = execute(EXAMPLE, settings=Settings(), output_dir=tmp_path / "one", state_dir=state)
    target = next(flag for flag in first.flags if flag.code == "usually_no_gst")
    set_note(state / "review-log.json", target.fingerprint, "ignored", "Bank fee was recoded", target.short_id)
    second = execute(EXAMPLE, settings=Settings(), output_dir=tmp_path / "two", state_dir=state)
    html = (tmp_path / "two" / "bas-gst-check.html").read_text(encoding="utf-8")
    assert "Bank fee was recoded" in html
    assert "Compared with the run" in html
    assert "Ignored" in html
