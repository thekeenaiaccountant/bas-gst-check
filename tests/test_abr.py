import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from bas_gst_check.abr import AbrTransportError, lookup_suppliers, parse_abr_body
from bas_gst_check.rules import load_rules
from tests.helpers import tx

RULES = load_rules()
FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "abr_responses.json").read_text(encoding="utf-8")
)


def guid() -> str:
    return "-".join(["ab12cd34", "ab12", "cd34", "ab12", "cd34ef567890"])


def fetch_recorded(url: str, timeout: float) -> str:
    abn = parse_qs(urlparse(url).query)["abn"][0]
    assert parse_qs(urlparse(url).query)["guid"][0] == guid()
    assert url.startswith("https://abr.business.gov.au/json/AbnDetails.aspx")
    return FIXTURES[abn]


def test_lookup_is_skipped_without_a_guid(tmp_path: Path):
    def explode(url: str, timeout: float) -> str:
        raise AssertionError("the ABR should not be called")

    outcome = lookup_suppliers([tx()], RULES, "", tmp_path / "cache.json", fetch=explode)
    assert outcome.mode == "off"
    assert outcome.flags == []
    assert "nothing was sent" in outcome.message.lower()


def test_bad_guid_shape_is_not_sent(tmp_path: Path):
    def explode(url: str, timeout: float) -> str:
        raise AssertionError("the ABR should not be called")

    outcome = lookup_suppliers(
        [tx()], RULES, "", tmp_path / "cache.json", bad_shape=True, fetch=explode
    )
    assert outcome.mode == "bad_shape"
    assert outcome.flags == []


def test_recorded_responses_cover_active_cancelled_and_unregistered(tmp_path: Path):
    purchases = [
        tx(supplier_abn="11111111111", description="Copy paper"),
        tx(supplier_abn="22222222222", description="Drawing table", net=Decimal("300.00"), gst=Decimal("30.00")),
        tx(supplier_abn="33333333333", description="Plugin licence", net=Decimal("150.00"), gst=Decimal("15.00")),
        tx(supplier_abn="44444444444", description="Site hosting", net=Decimal("140.00"), gst=Decimal("14.00")),
    ]
    outcome = lookup_suppliers(purchases, RULES, guid(), tmp_path / "cache.json", fetch=fetch_recorded)
    found = {flag.code for flag in outcome.flags}
    assert "abn_cancelled" in found
    assert "abn_not_gst_registered" in found
    assert "abn_not_found" in found
    assert not any(flag.transaction and flag.transaction.supplier_abn == "11111111111" for flag in outcome.flags)
    assert outcome.network_calls == 4


def test_cancelled_after_the_purchase_is_not_treated_as_cancelled_then(tmp_path: Path):
    body = (
        'callback({"Abn":"22222222222","AbnStatus":"Cancelled",'
        '"AbnStatusEffectiveFrom":"2026-08-01","Gst":"2018-07-01","EntityName":"Madeup Supplies","Message":""})'
    )
    record = parse_abr_body("22222222222", body)
    early = tx(date=date(2026, 7, 15), supplier_abn="22222222222")

    def fetch(url: str, timeout: float) -> str:
        return body

    outcome = lookup_suppliers([early], RULES, guid(), tmp_path / "cache.json", fetch=fetch)
    assert outcome.flags == []
    assert record.status == "cancelled"


def test_gst_registration_after_the_purchase_is_flagged(tmp_path: Path):
    body = (
        'callback({"Abn":"11111111111","AbnStatus":"Active",'
        '"AbnStatusEffectiveFrom":"2018-07-01","Gst":"2026-08-01","EntityName":"Madeup Supplies","Message":""})'
    )

    def fetch(url: str, timeout: float) -> str:
        return body

    outcome = lookup_suppliers(
        [tx(date=date(2026, 7, 15))],
        RULES,
        guid(),
        tmp_path / "cache.json",
        fetch=fetch,
    )
    assert [flag.code for flag in outcome.flags] == ["abn_not_gst_registered"]


def test_timeout_does_not_invent_a_finding_and_cache_avoids_a_second_call(tmp_path: Path):
    calls = {"n": 0}

    def fetch(url: str, timeout: float) -> str:
        calls["n"] += 1
        abn = parse_qs(urlparse(url).query)["abn"][0]
        if abn == "44444444444":
            raise AbrTransportError("timed out")
        return FIXTURES[abn]

    cache = tmp_path / "abr-cache.json"
    first = lookup_suppliers(
        [tx(supplier_abn="11111111111"), tx(supplier_abn="44444444444", description="Site hosting")],
        RULES,
        guid(),
        cache,
        fetch=fetch,
    )
    assert any("timed out" in note.reason for note in first.notes)
    assert not any(flag.code == "abn_not_found" for flag in first.flags)
    second = lookup_suppliers([tx()], RULES, guid(), cache, fetch=fetch)
    assert second.cache_hits == 1
    assert second.network_calls == 0
    assert calls["n"] == 2
    saved = cache.read_text(encoding="utf-8")
    assert guid() not in saved
    assert "Madeup Supplies" in saved


def test_rejected_guid_stops_the_check(tmp_path: Path):
    def fetch(url: str, timeout: float) -> str:
        return 'callback({"Message":"The GUID entered is not recognised as a Registered Party","Abn":""})'

    outcome = lookup_suppliers([tx()], RULES, guid(), tmp_path / "cache.json", fetch=fetch)
    assert outcome.mode == "rejected"
    assert outcome.flags == []
    assert guid() not in outcome.message
