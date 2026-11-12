import json
from pathlib import Path

from bas_gst_check.abn import abn_is_valid
from bas_gst_check.abr import probe_guid
from bas_gst_check.billread import abns_from_qr_payload, extract_labelled_abns, read_bills
from bas_gst_check.engine import execute
from bas_gst_check.learning import confirm_supplier, learning_path
from bas_gst_check.loaders import load_transactions
from bas_gst_check.rules import load_rules
from bas_gst_check.settings import Settings, save_abr_guid
from tests.test_abr import guid

BILLS = Path("examples/bills")


def test_only_a_labelled_abn_is_read():
    valid, invalid = extract_labelled_abns("Reference 99000000000\nABN: 99 000 000 000")
    assert valid == ["99000000000"]
    assert invalid == []
    assert abn_is_valid("99000000000")
    bad_valid, bad_invalid = extract_labelled_abns("ABN: 12 345 678 901")
    assert bad_valid == []
    assert bad_invalid == ["12345678901"]


def test_a_qr_payload_is_used_only_when_it_is_the_abn():
    assert abns_from_qr_payload("99000000000")[0] == ["99000000000"]
    assert abns_from_qr_payload("see you at 10") == ([], [])


def test_example_bills_cover_each_warning(tmp_path: Path):
    loaded = load_transactions(Path("examples/fennel-street-workshop.json"), load_rules())
    flags, hard, confirm = read_bills(BILLS, loaded.transactions)
    codes = {flag.code for flag in flags}
    assert {
        "bill_no_abn",
        "bill_bad_checksum",
        "bill_several_abns",
        "bill_unreadable",
        "bill_unmatched",
    } <= codes
    looked_up = {item[0] for item in confirm}
    assert "12345678901" not in looked_up
    assert "99000000000" in looked_up
    assert len(hard) >= 5


def test_confirmed_abn_is_remembered_and_not_an_image(tmp_path: Path):
    path = learning_path(tmp_path)
    message = confirm_supplier(path, "Cinder Repairs", "99000000000", hint="footer")
    assert "checksum" in message
    assert "99000000000" not in message
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert "image" not in saved
    blob = path.read_bytes()
    assert b"\x89PNG" not in blob
    refused = confirm_supplier(path, "Cinder Repairs", "12345678901")
    assert "not a valid ABN" in refused


def test_guid_shape_is_saved_only_when_it_matches_and_the_probe_is_offline(tmp_path: Path):
    settings_file = tmp_path / "my-settings.toml"
    try:
        save_abr_guid(settings_file, "not-a-guid")
    except ValueError as exc:
        assert "does not look" in str(exc)
    else:
        raise AssertionError("a bad GUID should not be saved")
    save_abr_guid(settings_file, guid())
    assert guid() in settings_file.read_text(encoding="utf-8")
    office = "51" + "824" + "753" + "556"
    body = (
        'callback({"Abn":"' + office + '","AbnStatus":"Active","AbnStatusEffectiveFrom":"1999-11-01",'
        '"EntityName":"AUSTRALIAN TAXATION OFFICE","Gst":"2000-07-01","Message":""})'
    )

    def fetch(url: str, timeout: float) -> str:
        assert guid() in url
        assert office in url
        return body

    ok, message = probe_guid(guid(), fetch=fetch)
    assert ok
    assert guid() not in message
    assert "GST-registered" in message
    failed, failure = probe_guid("nope", fetch=fetch)
    assert not failed
    assert "nope" not in failure


def test_skip_path_leaves_the_report_note(tmp_path: Path):
    folder = tmp_path / "bills"
    folder.mkdir()
    result = execute(
        Path("examples/fennel-street-workshop.json"),
        settings=Settings(),
        output_dir=tmp_path / "out",
        state_dir=tmp_path / "state",
        bills_dir=folder,
        fetch=lambda url, timeout: (_ for _ in ()).throw(AssertionError("network")),
    )
    html = (tmp_path / "out" / "bas-gst-check.html").read_text(encoding="utf-8")
    assert "ABN check is off" in html
    assert "set up ABN check" in html
    assert result.abr_mode == "off"
