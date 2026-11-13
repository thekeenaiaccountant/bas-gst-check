"""Run a check: read the file, flag lines, write the report, remember this run."""

from __future__ import annotations

import base64
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

from bas_gst_check.abr import confirm_bill_abns
from bas_gst_check.billread import read_bills
from bas_gst_check.billmatch import compare_bills
from bas_gst_check.checks import run_checks
from bas_gst_check.explain import explain_bas
from bas_gst_check.learning import (
    confirmed_abns,
    earlier_lines,
    hints,
    learning_path,
    load_learning,
    remember_hard,
    save_learning,
)
from bas_gst_check.loaders import LoadedFile, load_transactions
from bas_gst_check.models import Flag, Period, Summary
from bas_gst_check.report import PRESET, render_error_html, render_html, write_csv
from bas_gst_check.review_log import (
    assign_ids,
    compare,
    load_id_map,
    load_notes,
    load_previous,
    save_id_map,
    save_previous,
)
from bas_gst_check.rules import Rules, load_rules
from bas_gst_check.settings import Settings, load_settings
from bas_gst_check.suggestions import load_ai_suggestions, suggest_flags
from bas_gst_check.summarise import summarise
from bas_gst_check.suppliers import (
    account_totals,
    earlier_quarter,
    load_history,
    purchase_totals,
    remember_quarter,
    supplier_flags,
)

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "fennel-street-workshop.json"
EXAMPLE_BILLS = EXAMPLE.parent / "bills"
EXAMPLE_PREVIOUS = EXAMPLE.parent / "fennel-street-previous.json"
EXAMPLE_SUGGESTIONS = EXAMPLE.parent / "suggestions.json"
MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
}


@dataclass
class RunResult:
    html_path: Path | None
    csv_path: Path | None
    errors: list[str]
    summary: Summary | None
    flags: list[Flag]
    abr_mode: str


def execute(
    source: Path,
    *,
    settings: Settings | None = None,
    rules: Rules | None = None,
    output_dir: Path | None = None,
    state_dir: Path | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
    brand: str | None = None,
    fetch=None,
    bills_dir: Path | None = None,
    readings_path: Path | None = None,
    previous_path: Path | None = None,
    suggestions_path: Path | None = None,
) -> RunResult:
    active_settings = settings or load_settings()
    active_rules = _rules_with_overrides(rules or load_rules(), active_settings)
    if brand:
        active_settings = replace(active_settings, brand=brand)
    loaded = load_transactions(source, active_rules)
    output = output_dir or Path("output")
    state = state_dir or Path(".local")
    business = active_settings.business_name or loaded.business_name or "This business"
    if loaded.errors:
        html_path = _write_failure(output, business, loaded.errors, "pooja" if active_settings.brand == "preset" else "")
        return RunResult(html_path, None, loaded.errors, None, [], "off")

    period, warning = _resolve_period(loaded, active_settings, period_start, period_end)
    if period is None:
        missing = [
            "Which quarter is this file? For example, 1 July 2026 to 30 September 2026. "
            "The figures are not calculated until you name the period. Nothing was guessed from the dates in the file."
        ]
        html_path = _write_failure(output, business, missing, "pooja" if active_settings.brand == "preset" else "")
        return RunResult(html_path, None, missing, None, [], "off")
    warning = " ".join(part for part in (warning, _length_warning(period, active_settings.bas_period)) if part)
    basis = _basis(active_settings, loaded)
    summary = summarise(loaded.transactions, active_rules)
    flags = run_checks(loaded.transactions, period, active_rules)
    bill_folder = _bills_folder(source, bills_dir)
    learned = load_learning(learning_path(state))
    bill_flags, hard_notes, to_confirm, readings = read_bills(
        bill_folder,
        loaded.transactions,
        readings_path=readings_path,
        confirmed=confirmed_abns(learned),
        hints=hints(learned),
        rules=active_rules,
    ) if bill_folder else ([], [], [], [])
    flags.extend(compare_bills(readings, loaded.transactions, active_rules))
    suggestion_file, prior_file = _example_extras(source, suggestions_path, previous_path)
    flags.extend(suggest_flags(loaded.transactions, active_rules, load_ai_suggestions(suggestion_file)))
    prior_purchases, prior_accounts = _prior_totals(prior_file, state, period, active_rules)
    flags.extend(supplier_flags(loaded.transactions, prior_purchases, active_rules))
    flags.extend(bill_flags)
    hard_lines = remember_hard(learned, hard_notes)
    hard_lines.extend(earlier_lines(learned, {note.file_name for note in hard_notes}))
    if hard_notes or learned.get("hard"):
        save_learning(learning_path(state), learned)
    abr = confirm_bill_abns(
        to_confirm,
        active_rules,
        active_settings.abr_guid,
        state / "abr-cache.json",
        bad_shape=active_settings.abr_guid_rejected_shape,
        fetch=fetch,
    )
    flags.extend(abr.flags)
    notes = load_notes(state / "review-log.json")
    remembered = load_id_map(state / "flag-ids.json")
    remembered = assign_ids(flags, remembered)
    save_id_map(state / "flag-ids.json", remembered)
    previous = load_previous(state / "last-run.json")
    comparison = compare(previous, summary, flags)

    brand_overrides, brand_note = _brand(active_settings)
    if brand_note:
        warning = f"{warning} {brand_note}".strip()
    html = render_html(
        business=business,
        period=period,
        basis=basis,
        bas_period=active_settings.bas_period,
        fictional=loaded.fictional,
        summary=summary,
        flags=flags,
        notes=notes,
        comparison=comparison,
        abr=abr,
        rules=active_rules,
        logo_html=_logo(active_settings),
        brand_overrides=brand_overrides,
        period_warning=warning,
        hard_lines=hard_lines,
        bills_provided=bill_folder is not None,
        theme="pooja" if active_settings.brand == "preset" else "",
        timezone_name=active_settings.timezone,
        explanation=explain_bas(
            summary,
            purchase_totals(loaded.transactions),
            prior_purchases,
            account_totals(loaded.transactions),
            prior_accounts,
        ),
    )
    output.mkdir(parents=True, exist_ok=True)
    html_path = output / "bas-gst-check.html"
    csv_path = output / "flagged-items.csv"
    html_path.write_text(html, encoding="utf-8")
    write_csv(csv_path, flags, notes)
    save_previous(
        state / "last-run.json",
        summary,
        flags,
        period.start.isoformat(),
        period.end.isoformat(),
        business,
    )
    remember_quarter(
        state / "supplier-history.json",
        f"{period.start.isoformat()}:{period.end.isoformat()}",
        purchase_totals(loaded.transactions),
        account_totals(loaded.transactions),
    )
    return RunResult(html_path, csv_path, [], summary, flags, abr.mode)


def _example_extras(
    source: Path,
    suggestions_path: Path | None,
    previous_path: Path | None,
) -> tuple[Path | None, Path | None]:
    if source.name.startswith("fennel-street") and "previous" not in source.name:
        if suggestions_path is None and EXAMPLE_SUGGESTIONS.is_file():
            suggestions_path = EXAMPLE_SUGGESTIONS
        if previous_path is None and EXAMPLE_PREVIOUS.is_file():
            previous_path = EXAMPLE_PREVIOUS
    return suggestions_path, previous_path


def _prior_totals(previous_path: Path | None, state: Path, period: Period, rules: Rules):
    if previous_path is not None and previous_path.is_file():
        loaded = load_transactions(previous_path, rules)
        if not loaded.errors:
            return purchase_totals(loaded.transactions), account_totals(loaded.transactions)
    history = earlier_quarter(
        load_history(state / "supplier-history.json"),
        f"{period.start.isoformat()}:{period.end.isoformat()}",
    )
    if history is None:
        return None, None
    return history


def _bills_folder(source: Path, bills_dir: Path | None) -> Path | None:
    if bills_dir is not None:
        return bills_dir if bills_dir.is_dir() else None
    if source.name.startswith("fennel-street") and EXAMPLE_BILLS.is_dir():
        return EXAMPLE_BILLS
    return None


def _rules_with_overrides(rules: Rules, settings: Settings) -> Rules:
    return replace(
        rules,
        tolerance=settings.tolerance or rules.tolerance,
        tax_invoice_threshold=settings.tax_invoice_threshold or rules.tax_invoice_threshold,
        capital_threshold=settings.capital_threshold or rules.capital_threshold,
    )


def _resolve_period(
    loaded: LoadedFile,
    settings: Settings,
    start: date | None,
    end: date | None,
) -> tuple[Period | None, str]:
    if start and end:
        return Period(start, end, inferred=False), ""
    if settings.period_start and settings.period_end:
        return Period(settings.period_start, settings.period_end), ""
    if loaded.period_start and loaded.period_end:
        return Period(loaded.period_start, loaded.period_end), ""
    return None, ""


def _write_failure(output: Path, business: str, errors: list[str], theme: str = "") -> Path:
    output.mkdir(parents=True, exist_ok=True)
    html_path = output / "bas-gst-check.html"
    html_path.write_text(render_error_html(business or "This business", errors, theme), encoding="utf-8")
    return html_path


def _length_warning(period: Period, bas_period: str) -> str:
    days = (period.end - period.start).days + 1
    if bas_period == "quarterly" and not 80 <= days <= 100:
        return f"This period covers {days} days, which is an unusual length for a quarterly BAS."
    if bas_period == "monthly" and not 28 <= days <= 31:
        return f"This period covers {days} days, which is an unusual length for a monthly BAS."
    return ""


def _basis(settings: Settings, loaded: LoadedFile) -> str:
    if settings.source and settings.gst_basis:
        return settings.gst_basis
    if loaded.gst_basis in {"cash", "accrual"}:
        return loaded.gst_basis
    return settings.gst_basis or "accrual"


def _brand(settings: Settings) -> tuple[dict[str, str], str]:
    if settings.brand == "preset":
        return dict(PRESET), ""
    if settings.brand == "custom":
        if not settings.primary or not settings.accent:
            return {}, "Custom branding was selected without both colours, so the report uses the default ink and paper."
        return {"--primary": settings.primary, "--accent": settings.accent, "--ink": settings.primary}, ""
    return {}, ""


def _logo(settings: Settings) -> str:
    if not settings.logo:
        return ""
    brand_dir = (Path.cwd() / "my-brand").resolve()
    candidate = (brand_dir / settings.logo).resolve()
    try:
        candidate.relative_to(brand_dir)
    except ValueError:
        return ""
    if candidate.suffix.lower() not in MIME or not candidate.is_file():
        return ""
    if candidate.stat().st_size > 1_500_000:
        return ""
    encoded = base64.b64encode(candidate.read_bytes()).decode("ascii")
    mime = MIME[candidate.suffix.lower()]
    return f'<img class="logo" alt="" src="data:{mime};base64,{encoded}">'
