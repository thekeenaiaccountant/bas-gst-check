"""Plain-English command line. The desktop apps call this; people do not have to."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from bas_gst_check import __version__
from bas_gst_check.abr import probe_guid
from bas_gst_check.engine import EXAMPLE, execute
from bas_gst_check.learning import confirm_supplier, learning_path
from bas_gst_check.review_log import load_previous, set_note
from bas_gst_check.settings import load_settings, save_abr_guid, settings_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bas-gst-check",
        description="Check a quarter of GST figures before the BAS is lodged. Nothing is lodged.",
    )
    parser.add_argument("--version", action="version", version=f"bas-gst-check {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    run_parser = commands.add_parser("run", help="Check a JSON or CSV file and write a report")
    run_parser.add_argument("file", nargs="?", help="Path to the transactions file")
    run_parser.add_argument("--example", action="store_true", help="Use the fictional example quarter")
    run_parser.add_argument("--from", dest="date_from", help="Period start, YYYY-MM-DD")
    run_parser.add_argument("--to", dest="date_to", help="Period end, YYYY-MM-DD")
    run_parser.add_argument("--brand", choices=["skip", "preset", "custom"])
    run_parser.add_argument("--output", default="output")
    run_parser.add_argument("--state", default=".local")
    run_parser.add_argument("--bills", help="Folder of supplier bills (PDF or photo)")
    run_parser.add_argument("--readings", help="JSON of text read from bills by Claude or Codex")
    run_parser.add_argument("--previous", help="Previous quarter export, for new suppliers and spend changes")
    run_parser.add_argument("--suggestions", help="JSON of GST-code suggestions from Claude or Codex")

    note_parser = commands.add_parser("note", help="Mark a flag fixed, ignored, or open again")
    note_parser.add_argument("flag_id", help="The id from the latest report, such as F-01")
    note_parser.add_argument("--status", required=True, choices=["fixed", "ignored", "open"])
    note_parser.add_argument("--note", default="")
    note_parser.add_argument("--state", default=".local")

    commands.add_parser("save-guid", help="Read an ABR GUID from stdin, save it, and test it")
    commands.add_parser("check-guid", help="Test the saved ABR GUID without printing it")

    confirm_parser = commands.add_parser("confirm-abn", help="Remember an ABN the user confirmed")
    confirm_parser.add_argument("--supplier", required=True)
    confirm_parser.add_argument("--abn", required=True)
    confirm_parser.add_argument("--hint", default="")
    confirm_parser.add_argument("--state", default=".local")

    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            return _run(args)
        if args.command == "note":
            return _note(args)
        if args.command == "save-guid":
            return _save_guid()
        if args.command == "check-guid":
            return _check_guid()
        if args.command == "confirm-abn":
            print(confirm_supplier(learning_path(Path(args.state)), args.supplier, args.abn, args.hint))
            return 0
    except (OSError, ValueError) as exc:
        print(exc)
        return 1
    print("Unknown command.")
    return 1


def _run(args: argparse.Namespace) -> int:
    settings = load_settings()
    path = _choose_file(args, settings.data_file)
    start = date.fromisoformat(args.date_from) if args.date_from else None
    end = date.fromisoformat(args.date_to) if args.date_to else None
    if (start is None) != (end is None):
        print("Give both a start date and an end date, or neither.")
        return 1
    result = execute(
        path,
        settings=settings,
        output_dir=Path(args.output),
        state_dir=Path(args.state),
        period_start=start,
        period_end=end,
        brand=args.brand,
        bills_dir=Path(args.bills) if args.bills else None,
        readings_path=Path(args.readings) if args.readings else None,
        previous_path=Path(args.previous) if args.previous else None,
        suggestions_path=Path(args.suggestions) if args.suggestions else None,
    )
    if result.errors:
        print("The file could not be checked.")
        for error in result.errors:
            print(f"- {error}")
        return 1
    errors = sum(1 for flag in result.flags if flag.severity == "error")
    invoices = sum(1 for flag in result.flags if flag.code == "tax_invoice")
    hints = sum(1 for flag in result.flags if flag.severity == "review" and flag.code != "tax_invoice")
    print(f"HTML report: {result.html_path}")
    print(f"Flagged rows: {result.csv_path}")
    print(
        f"Lines to fix: {errors}. Tax invoices to have on file: {invoices}. "
        f"Suggestions to check: {hints}. Those reminders are not mistakes."
    )
    if result.summary:
        print(
            f"Draft net GST: {result.summary.net} "
            f"({result.summary.position})."
        )
    return 0


def _save_guid() -> int:
    raw = sys.stdin.read().strip()
    if not raw:
        print("No GUID was received. Paste it again, or say skip for now.")
        return 1
    try:
        save_abr_guid(settings_path(), raw)
    except ValueError as exc:
        print(exc)
        return 1
    settings = load_settings()
    _ok, message = probe_guid(settings.abr_guid)
    print("Saved the GUID in my-settings.toml. It is not shown here.")
    print(message)
    return 0 if _ok else 1


def _check_guid() -> int:
    settings = load_settings()
    if settings.abr_guid_rejected_shape:
        print('ABN check is off: say "set up ABN check" to turn it on. The saved value does not look like an ABR GUID.')
        return 1
    if not settings.abr_guid:
        print('ABN check is off: say "set up ABN check" to turn it on.')
        return 1
    ok, message = probe_guid(settings.abr_guid)
    print(message)
    return 0 if ok else 1


def _choose_file(args: argparse.Namespace, configured: str) -> Path:
    if args.example:
        return EXAMPLE
    if args.file:
        return Path(args.file)
    if configured:
        return Path(configured)
    print("No file was named, so this run uses the fictional example.")
    return EXAMPLE


def _note(args: argparse.Namespace) -> int:
    state = Path(args.state)
    previous = load_previous(state / "last-run.json")
    if not previous:
        print("There is no saved run yet. Run the check first, then mark a flag from that report.")
        return 1
    wanted = args.flag_id.strip().upper()
    match = next((item for item in previous.get("flags", []) if str(item.get("id", "")).upper() == wanted), None)
    if not match:
        print(f"{args.flag_id} is not in the latest report. Use the id printed there.")
        return 1
    set_note(
        state / "review-log.json",
        str(match["fingerprint"]),
        args.status,
        args.note,
        str(match.get("label") or wanted),
    )
    if args.status == "open":
        print(f"{wanted} is open again. The next report will treat it as new work.")
    else:
        print(f"{wanted} marked {args.status}. The next report will show that note.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
