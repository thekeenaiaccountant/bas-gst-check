from bas_gst_check.report import format_local
from bas_gst_check.settings import Settings, load_settings
from pathlib import Path


def test_since_last_time_uses_sydney_by_default():
    shown = format_local("2026-11-13T00:44:00+00:00")
    assert shown == "13 November 2026, 11:44am AEDT"
    winter = format_local("2026-07-13T00:44:00+00:00", "Australia/Sydney")
    assert winter == "13 July 2026, 10:44am AEST"


def test_timezone_can_be_set_in_settings(tmp_path: Path):
    path = tmp_path / "my-settings.toml"
    path.write_text('timezone = "Australia/Perth"\nbas_period = "quarterly"\ngst_basis = "accrual"\nbrand = "skip"\n', encoding="utf-8")
    settings = load_settings(path)
    assert settings.timezone == "Australia/Perth"
    assert format_local("2026-11-13T00:44:00+00:00", settings.timezone) == "13 November 2026, 8:44am AWST"
    assert Settings().timezone == "Australia/Sydney"
