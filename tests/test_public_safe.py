import importlib.util
import sys
from pathlib import Path

SCANNER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_public_safe.py"
SPEC = importlib.util.spec_from_file_location("check_public_safe", SCANNER_PATH)
assert SPEC and SPEC.loader
scanner = importlib.util.module_from_spec(SPEC)
sys.modules["check_public_safe"] = scanner
SPEC.loader.exec_module(scanner)


def test_detectors_catch_private_patterns_and_ignore_fiction():
    email = "studio" + "@" + "example.test"
    phone = "04" + "38" + " " + "221" + " " + "904"
    secret_path = "/" + "Users" + "/" + "someone" + "/notes"
    token = "-".join(["ab12cd34", "ab12", "cd34", "ab12", "cd34ef567890"])
    person = "John" + " " + "Smith"
    assert scanner.find_in_text(email)
    assert scanner.find_in_text(phone)
    assert scanner.find_in_text(secret_path)
    assert scanner.find_in_text(token)
    assert scanner.find_in_text(person)
    assert scanner.find_in_text('abr_guid = ""') == []
    assert scanner.find_in_text("supplier_abn 11111111111") == []
    valid = _valid_abn()
    assert scanner.find_in_text(valid)


def test_repo_scan_is_clean():
    root = Path(__file__).resolve().parents[1]
    assert scanner.scan(root) == 0


def _valid_abn() -> str:
    weights = (10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19)
    for number in range(10_000_000_000, 10_000_002_000):
        digits = [int(character) for character in f"{number:011d}"]
        trial = digits.copy()
        trial[0] -= 1
        if trial[0] < 0:
            continue
        if sum(digit * weight for digit, weight in zip(trial, weights)) % 89 == 0:
            return f"{number:011d}"
    raise AssertionError("could not build a checksum sample")
