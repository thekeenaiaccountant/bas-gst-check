"""Plain-English command line. The desktop apps call this; people do not have to."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from bas_gst_check import __version__
from bas_gst_check.engine import EXAMPLE, execute
from bas_gst_check.review_log import load_previous, set_note
from bas_gst_check.settings import load_settings


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

    note_parser = commands.add_parser("note", help="Mark a flag fixed, ignored, or open again")
    note_parser.add_argument("flag_id", help="The id from the latest report, such as F-01")
    note_parser.add_argument("--status", required=True, choices=["fixed", "ignored", "open"])
    note_parser.add_argument("--note", default="")
    note_parser.add_argument("--state", default=".local")

    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            return _run(args)
        if args.command == "note":
            return _note(args)
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
    )
    if result.errors:
        print("The file could not be checked.")
        for error in result.errors:
            print(f"- {error}")
        return 1
    errors = sum(1 for flag in result.flags if flag.severity == "error")
    reviews = sum(1 for flag in result.flags if flag.severity == "review")
    print(f"HTML report: {result.html_path}")
    print(f"Flagged rows: {result.csv_path}")
    print(f"Flags: {errors} likely mistakes, {reviews} tax-invoice reminders.")
    if result.summary:
        print(
            f"Draft net GST: {result.summary.net} "
            f"({result.summary.position})."
        )
    return 0


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
