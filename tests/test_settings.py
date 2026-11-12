from pathlib import Path

from bas_gst_check.settings import load_settings


def guid() -> str:
    return "-".join(["ab12cd34", "ab12", "cd34", "ab12", "cd34ef567890"])


def test_example_settings_keep_the_guid_empty():
    settings = load_settings(Path("my-settings.example.toml"))
    assert settings.abr_guid == ""
    assert settings.abr_guid_rejected_shape is False
    assert settings.brand == "skip"


def test_environment_guid_is_accepted(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("ABR_GUID", guid())
    settings = load_settings(tmp_path / "absent.toml")
    assert settings.abr_guid == guid()


def test_a_value_that_is_not_a_guid_is_not_stored(tmp_path: Path):
    path = tmp_path / "my-settings.toml"
    path.write_text(
        'business_name = ""\nbas_period = "quarterly"\ngst_basis = "accrual"\n'
        'brand = "skip"\nabr_guid = "not-a-guid"\n',
        encoding="utf-8",
    )
    settings = load_settings(path)
    assert settings.abr_guid == ""
    assert settings.abr_guid_rejected_shape is True
