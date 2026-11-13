"""Self-contained HTML report and CSV of flagged lines."""

from __future__ import annotations

import csv
import html
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pathlib import Path
from string import Template

from bas_gst_check.abr import AbrOutcome, SupplierLine
from bas_gst_check.checks import period_label
from bas_gst_check.models import Comparison, Flag, Note, Period, Summary, Transaction
from bas_gst_check.money import money_text
from bas_gst_check.rules import Rules
from bas_gst_check.sources import (
    ACCOUNTING_METHOD,
    GST_CREDIT,
    METHODS,
    PURCHASES,
    SALES,
    SOURCE_TITLES,
    SUMMARY,
    TAX_INVOICE,
)

PACKAGE_TEMPLATES = Path(__file__).resolve().parent / "templates"

PRESET = {
    "--ink": "#021A54",
    "--primary": "#021A54",
    "--accent": "#FF85BB",
    "--paper": "#FFFFFF",
    "--card": "#FFFFFF",
    "--line": "#E2E6EE",
    "--muted": "#5B6B8F",
    "--good": "#0E7A43",
    "--warn": "#9A5B00",
    "--bad": "#9B1C1C",
    "--serif": "Inter, \"Segoe UI\", sans-serif",
    "--sans": "Inter, \"Segoe UI\", sans-serif",
}


def render_html(
    *,
    business: str,
    period: Period,
    basis: str,
    bas_period: str,
    fictional: bool,
    summary: Summary,
    flags: list[Flag],
    notes: dict[str, Note],
    comparison: Comparison,
    abr: AbrOutcome,
    rules: Rules,
    logo_html: str,
    brand_overrides: dict[str, str],
    period_warning: str,
    hard_lines: list[str] | None = None,
    bills_provided: bool = False,
    theme: str = "",
    timezone_name: str = "Australia/Sydney",
) -> str:
    css = (PACKAGE_TEMPLATES / "report.css").read_text(encoding="utf-8")
    if brand_overrides:
        lines = [f"  {name}: {value};" for name, value in brand_overrides.items()]
        css += "\n:root {\n" + "\n".join(lines) + "\n}\n"
    extra = Path.cwd() / "my-templates" / "extra.css"
    if extra.is_file():
        css += "\n" + extra.read_text(encoding="utf-8")
    body = _body(
        business=business,
        period=period,
        basis=basis,
        bas_period=bas_period,
        fictional=fictional,
        summary=summary,
        flags=flags,
        notes=notes,
        comparison=comparison,
        abr=abr,
        rules=rules,
        logo_html=logo_html,
        period_warning=period_warning,
        hard_lines=hard_lines or [],
        bills_provided=bills_provided,
        timezone_name=timezone_name,
    )
    template_path = Path.cwd() / "my-templates" / "report.html.tpl"
    if not template_path.is_file():
        template_path = PACKAGE_TEMPLATES / "report.html.tpl"
    template = Template(template_path.read_text(encoding="utf-8"))
    title = f"BAS GST check — {business}"
    return template.substitute(
        title=html.escape(title),
        css=css,
        body=body,
        body_class="pooja" if theme == "pooja" else "",
    )


def write_csv(path: Path, flags: list[Flag], notes: dict[str, Note]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "flag_id",
        "check",
        "severity",
        "date",
        "type",
        "contact",
        "description",
        "account",
        "tax_code",
        "net_amount",
        "gst_amount",
        "inclusive_amount",
        "supplier_abn",
        "reference",
        "why",
        "suggested_fix",
        "review_status",
        "review_note",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for flag in flags:
            transaction = flag.transaction
            note = notes.get(flag.fingerprint)
            writer.writerow({
                "flag_id": flag.short_id,
                "check": flag.code,
                "severity": flag.severity,
                "date": transaction.date.isoformat() if transaction else "",
                "type": transaction.side if transaction else "",
                "contact": transaction.contact if transaction else "",
                "description": transaction.description if transaction else "",
                "account": transaction.account if transaction else "",
                "tax_code": transaction.tax_code_label if transaction else "",
                "net_amount": transaction.net if transaction else "",
                "gst_amount": transaction.gst if transaction else "",
                "inclusive_amount": transaction.inclusive if transaction else "",
                "supplier_abn": transaction.supplier_abn if transaction else "",
                "reference": transaction.reference if transaction else "",
                "why": flag.why,
                "suggested_fix": flag.fix,
                "review_status": note.status if note else "",
                "review_note": note.text if note else "",
            })


@dataclass(frozen=True)
class SupplierRow:
    date: str
    supplier: str
    amount: str
    gst: str
    abn: str
    action: str


MISSING_BILL_CODES = frozenset({
    "bill_no_abn",
    "bill_unreadable",
    "bill_bad_checksum",
    "bill_several_abns",
})
RED_FLAG = {"cancelled": "abn_cancelled", "not_registered": "abn_not_gst_registered"}
ROW_ACTION = {
    "cancelled": "Take the GST out of 1B. The ABR shows this ABN as cancelled.",
    "not_registered": "Take the GST out of 1B. The ABR shows no GST registration on this date.",
    "not_found": "The ABR has no record of this ABN. Check the digits before claiming GST.",
    "unchecked": "ABN is on the bill. GST registration was not checked.",
    "gst_registered": "ABN is active and the supplier was GST-registered on this date.",
    "could_not_check": "The ABR did not answer. No conclusion was drawn.",
    "bill_no_abn": "No ABN on the bill. Ask the supplier, or leave the GST out of 1B.",
    "bill_unreadable": "This bill could not be read. Ask Claude or Codex to read it, or send a text PDF.",
    "bill_bad_checksum": "The ABN on the bill fails the checksum. Read the digits again.",
    "bill_several_abns": "This bill shows more than one ABN. Say which one is the supplier's.",
    "bill_unmatched": "This bill did not match a purchase in the file. Check the supplier, date and total.",
}


def section_heading(kind: str, count: int, checked: bool) -> str:
    names = {
        "problem": (
            "Not registered for GST, but GST was claimed"
            if checked
            else "Couldn't check GST registration"
        ),
        "missing": "ABN not found",
        "registered": "ABN found and GST registered",
    }
    try:
        name = names[kind]
    except KeyError as exc:
        raise ValueError(f"unknown supplier section {kind}") from exc
    return f"{name} ({count})"


def supplier_sections(
    flags: list[Flag],
    abr: AbrOutcome,
    notes: dict[str, Note] | None = None,
) -> tuple[list[SupplierRow], list[SupplierRow], list[SupplierRow], bool]:
    """Group bill lines into not-registered, ABN missing, and GST-registered."""
    remembered = notes or {}
    checked = abr.mode == "on"
    problem: list[SupplierRow] = []
    missing: list[SupplierRow] = []
    registered: list[SupplierRow] = []
    if checked:
        covered_missing = {line.file_name for line in abr.lines if line.outcome == "not_found"}
        for line in abr.lines:
            if line.outcome in RED_FLAG and _gst_claimed(line.transaction):
                problem.append(_row_from_line(line, flags, remembered))
            elif line.outcome == "not_found":
                missing.append(_row_from_line(line, flags, remembered))
            elif line.outcome == "gst_registered":
                registered.append(_row_from_line(line, flags, remembered))
        for flag in flags:
            if flag.code == "abn_not_found" and flag.detail_key not in covered_missing:
                missing.append(_row_from_flag(flag, remembered))
    else:
        for line in abr.lines:
            if line.abn:
                problem.append(_row_from_line(line, flags, remembered, ROW_ACTION["unchecked"]))
    for flag in flags:
        if flag.code in MISSING_BILL_CODES:
            missing.append(_row_from_flag(flag, remembered))
    return problem, missing, registered, checked


def other_flags(flags: list[Flag], abr: AbrOutcome) -> list[Flag]:
    """Flags that are not already a row in the three supplier sections."""
    shown_red: set[int] = set()
    if abr.mode == "on":
        for line in abr.lines:
            if line.outcome in RED_FLAG and _gst_claimed(line.transaction) and line.transaction is not None:
                shown_red.add(id(line.transaction))
    hidden = set(MISSING_BILL_CODES)
    hidden.add("abn_not_found")
    kept: list[Flag] = []
    for flag in flags:
        if flag.code in hidden:
            continue
        if (
            flag.code in {"abn_cancelled", "abn_not_gst_registered"}
            and flag.transaction is not None
            and id(flag.transaction) in shown_red
        ):
            continue
        kept.append(flag)
    return kept



def _body(
    *,
    business: str,
    period: Period,
    basis: str,
    bas_period: str,
    fictional: bool,
    summary: Summary,
    flags: list[Flag],
    notes: dict[str, Note],
    comparison: Comparison,
    abr: AbrOutcome,
    rules: Rules,
    logo_html: str,
    period_warning: str,
    hard_lines: list[str],
    bills_provided: bool,
    timezone_name: str,
) -> str:
    problem, missing, registered, checked = supplier_sections(flags, abr, notes)
    parts = [
        '<main class="wrap">',
        _header(business, period, basis, bas_period, logo_html),
        _figures(summary),
    ]
    if period_warning:
        parts.append(f'<p class="quiet">{html.escape(period_warning)}</p>')
    if summary.left_out:
        noun = "line was" if summary.left_out == 1 else "lines were"
        parts.append(
            f'<p class="quiet">{summary.left_out} {noun} left out because the tax code or the sale/purchase side '
            "was not recognised. This is not a nil BAS.</p>"
        )
    if not checked:
        parts.append(
            '<p class="guidline">GST registration could not be checked. '
            'ABN check is off: say "set up ABN check" to turn it on.</p>'
        )
    parts.append(_status("bad", "problem", problem, checked))
    parts.append(_status("warn", "missing", missing, checked))
    parts.append(_fold("good", "registered", registered, checked, _table(registered)))
    parts.append(_other(flags, notes, comparison, abr, rules, basis, hard_lines, bills_provided, timezone_name))
    parts.append(_footer(fictional))
    parts.append("</main>")
    return "\n".join(parts)


def _header(business: str, period: Period, basis: str, bas_period: str, logo_html: str) -> str:
    basis_label = "Cash" if basis == "cash" else "Accrual"
    rhythm = "Quarterly" if bas_period == "quarterly" else "Monthly"
    return f"""
<header class="top">
  <div>
    {logo_html}
    <h1>{html.escape(business)}</h1>
    <p class="lede">{html.escape(period_label(period.start, period.end))} · {rhythm} · {basis_label}</p>
  </div>
  <p class="tag">Check only</p>
</header>
"""


def _figures(summary: Summary) -> str:
    unusable = summary.left_out and summary.g1 == 0 and summary.gst_on_sales == 0 and summary.gst_on_purchases == 0
    if unusable:
        position = "Not a usable BAS"
        position_class = ""
        net = money_text(summary.net)
    else:
        position = {"payable": "Payable", "refundable": "Refundable", "nil": "Nil"}[summary.position]
        position_class = " good" if summary.position == "refundable" else ""
        net = money_text(abs(summary.net)) if summary.position != "nil" else money_text(summary.net)
    return f"""
<section class="figures" aria-label="Draft BAS summary">
  <article class="figure"><span>G1 total sales</span><strong>{money_text(summary.g1)}</strong></article>
  <article class="figure"><span>1A GST on sales</span><strong>{money_text(summary.gst_on_sales)}</strong></article>
  <article class="figure"><span>1B GST on purchases</span><strong>{money_text(summary.gst_on_purchases)}</strong></article>
  <article class="figure"><span>Net GST</span><strong>{net}</strong><em class="{position_class.strip()}">{position}</em></article>
</section>
<p class="splitline"><span>G10 capital</span> <strong>{money_text(summary.g10)}</strong> · <span>G11 non-capital</span> <strong>{money_text(summary.g11)}</strong></p>
"""


def _status(tone: str, kind: str, rows: list[SupplierRow], checked: bool) -> str:
    return (
        f'<section class="status {tone}">'
        f"<h2>{section_heading(kind, len(rows), checked)}</h2>"
        f"{_table(rows)}"
        "</section>"
    )


def _fold(tone: str, kind: str, rows: list[SupplierRow], checked: bool, inner: str) -> str:
    return (
        f'<details class="fold {tone}">'
        f"<summary>{section_heading(kind, len(rows), checked)}</summary>"
        f'<div class="inside">{inner}</div>'
        "</details>"
    )


def _table(rows: list[SupplierRow]) -> str:
    if not rows:
        return '<p class="empty">None in this file.</p>'
    body = "".join(
        "<tr>"
        f"<td>{html.escape(row.date)}</td>"
        f"<td>{html.escape(row.supplier)}</td>"
        f"<td class='num'>{html.escape(row.amount)}</td>"
        f"<td class='num'>{html.escape(row.gst)}</td>"
        f"<td class='abn'>{html.escape(row.abn)}</td>"
        f"<td>{html.escape(row.action)}</td>"
        "</tr>"
        for row in rows
    )
    return (
        '<div class="table-wrap"><table><thead><tr>'
        "<th>Date</th><th>Supplier</th><th class='num'>Amount</th>"
        "<th class='num'>GST in the file</th><th>ABN</th><th>What to do</th>"
        f"</tr></thead><tbody>{body}</tbody></table></div>"
    )


def _other(
    flags: list[Flag],
    notes: dict[str, Note],
    comparison: Comparison,
    abr: AbrOutcome,
    rules: Rules,
    basis: str,
    hard_lines: list[str],
    bills_provided: bool,
    timezone_name: str,
) -> str:
    kept = other_flags(flags, abr)
    pending = [line for line in abr.lines if line.outcome == "could_not_check"]
    count = len(kept) + len(pending)
    groups: list[tuple[str, list[Flag]]] = []
    index: dict[str, int] = {}
    for flag in kept:
        slot = index.get(flag.title)
        if slot is None:
            index[flag.title] = len(groups)
            groups.append((flag.title, [flag]))
        else:
            groups[slot][1].append(flag)
    blocks = [_since(comparison, timezone_name)]
    if not bills_provided:
        blocks.append("<p>No bills folder was included, so no supplier ABN was read from a document.</p>")
    if hard_lines:
        noun = "bill was" if len(hard_lines) == 1 else "bills were"
        blocks.append(f"<p>{len(hard_lines)} hard {noun} saved on this computer for next time.</p>")
    if not kept and not pending:
        blocks.append('<p class="empty">Nothing else was flagged.</p>')
    for title, items in groups:
        rows = [_row_from_flag(flag, notes) for flag in items]
        blocks.append(f"<h3>{html.escape(title)} ({len(items)})</h3>")
        blocks.append(_table(rows))
    if pending:
        rows = [_row_from_line(line, flags, notes) for line in pending]
        blocks.append(f"<h3>Could not check this ABN ({len(pending)})</h3>")
        blocks.append(_table(rows))
    basis_text = (
        "Cash basis: only money received or paid in this period belongs in these totals."
        if basis == "cash"
        else "Accrual basis: invoices and bills for this period belong in these totals."
    )
    blocks.append(
        f"<p>{html.escape(basis_text)} "
        f"A one-eleventh difference above {money_text(rules.tolerance)} is listed above. "
        "G1 includes GST. 1A and 1B are the GST recorded in the file. Simpler BAS lodges G1, 1A and 1B only.</p>"
    )
    blocks.append("<h3>Sources</h3>")
    blocks.append(_sources())
    inner = "".join(blocks)
    return (
        f'<details class="fold other">'
        f"<summary>Other checks ({count})</summary>"
        f'<div class="inside">{inner}</div>'
        "</details>"
    )


def _since(comparison: Comparison, timezone_name: str) -> str:
    if not comparison.has_previous:
        return (
            "<h3>Since last time</h3>"
            "<p>This is the first run saved on this computer. "
            "The next run will show what moved in the draft figures and which flags disappeared.</p>"
        )
    labels = {"g1": "G1", "gst_on_sales": "1A", "gst_on_purchases": "1B", "net": "Net GST"}
    bits = []
    for key, label in labels.items():
        delta = comparison.deltas.get(key)
        if delta is None or delta == 0:
            bits.append(f"{label} unchanged")
        else:
            bits.append(f"{label} {money_text(delta)}")
    cleared = ""
    if comparison.cleared_labels:
        items = "".join(f"<li>{html.escape(label)}</li>" for label in comparison.cleared_labels[:12])
        more = ""
        if len(comparison.cleared_labels) > 12:
            more = f"<li>and {len(comparison.cleared_labels) - 12} more</li>"
        cleared = f"<p>Cleared since last time:</p><ul class='clean'>{items}{more}</ul>"
    new_count = len(comparison.new_flags)
    return (
        "<h3>Since last time</h3>"
        f"<p>Compared with the run on {html.escape(format_local(comparison.previous_at, timezone_name))}.</p>"
        f"<p class='delta'>{html.escape('; '.join(bits))}.</p>"
        f"<p>{new_count} new flag{'s' if new_count != 1 else ''}. "
        f"{comparison.still_open} still open from last time. "
        f"{len(comparison.cleared_labels)} cleared.</p>"
        f"{cleared}"
    )


def _footer(fictional: bool) -> str:
    parts = ["Not tax advice.", "GST part of the BAS only."]
    if fictional:
        parts.append("These figures are made-up example data.")
    parts.append("Do not email this folder.")
    return f'<footer class="end"><p>{" ".join(parts)}</p></footer>'


def _gst_claimed(transaction: Transaction | None) -> bool:
    return transaction is not None and transaction.gst > 0


def _row_from_line(
    line: SupplierLine,
    flags: list[Flag],
    notes: dict[str, Note],
    action: str | None = None,
) -> SupplierRow:
    flag = _match_flag(flags, line)
    text = action or ROW_ACTION.get(line.outcome, "Check this supplier before the GST stays in 1B.")
    return _display_row(
        line.transaction,
        line.on_date,
        line.supplier,
        None,
        None,
        line.abn,
        _with_flag(text, flag, notes),
    )


def _row_from_flag(flag: Flag, notes: dict[str, Note]) -> SupplierRow:
    text = ROW_ACTION.get(flag.code, flag.fix)
    abn = flag.line_abn
    if flag.code not in MISSING_BILL_CODES and not abn and flag.transaction is not None:
        abn = flag.transaction.supplier_abn
    return _display_row(
        flag.transaction,
        flag.line_date,
        flag.supplier_name,
        flag.line_amount,
        flag.line_gst,
        abn,
        _with_flag(text, flag, notes),
    )


def _display_row(
    transaction: Transaction | None,
    when: date | None,
    supplier: str,
    amount: Decimal | None,
    gst: Decimal | None,
    abn: str,
    action: str,
) -> SupplierRow:
    if transaction is not None:
        when = transaction.date
        supplier = transaction.contact or supplier
        amount = transaction.inclusive
        gst = transaction.gst
    return SupplierRow(
        date=_date_text(when),
        supplier=supplier or "—",
        amount=_money_or_dash(amount),
        gst=_money_or_dash(gst),
        abn=_abn_text(abn),
        action=action,
    )


def _match_flag(flags: list[Flag], line: SupplierLine) -> Flag | None:
    code = RED_FLAG.get(line.outcome)
    if line.outcome == "not_found":
        code = "abn_not_found"
    if not code:
        return None
    for flag in flags:
        if flag.code != code:
            continue
        if line.transaction is not None and flag.transaction is line.transaction:
            return flag
        if line.file_name and flag.detail_key == line.file_name:
            return flag
    return None


def _with_flag(action: str, flag: Flag | None, notes: dict[str, Note]) -> str:
    if flag is None:
        return action
    prefix = f"{flag.short_id}. " if flag.short_id else ""
    note = notes.get(flag.fingerprint) if flag.fingerprint else None
    if note is None:
        return f"{prefix}{action}"
    label = "Ignored" if note.status == "ignored" else "Marked fixed"
    extra = f" {note.text}" if note.text else ""
    return f"{prefix}{label}.{extra} {action}".strip()


def _date_text(value: date | None) -> str:
    if value is None:
        return "—"
    return f"{value.day} {value.strftime('%b %Y')}"


def _money_or_dash(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return money_text(value)


def _abn_text(value: str) -> str:
    digits = "".join(character for character in (value or "") if character.isdigit())
    if len(digits) != 11:
        return "—"
    return f"{digits[0:2]} {digits[2:5]} {digits[5:8]} {digits[8:11]}"


def _sources() -> str:
    pages = [SALES, SUMMARY, PURCHASES, METHODS, TAX_INVOICE, GST_CREDIT, ACCOUNTING_METHOD]
    items = "".join(
        f'<li><a href="{html.escape(url)}">{html.escape(SOURCE_TITLES[url])}</a></li>'
        for url in pages
    )
    return f'<ul class="sources">{items}</ul>'



def render_error_html(business: str, errors: list[str], theme: str = "") -> str:
    items = "".join(f"<li>{html.escape(error)}</li>" for error in errors)
    body = f"""
<main class="wrap">
  <header class="top"><h1>{html.escape(business)}</h1><p class="tag">Check only</p></header>
  <section class="status bad"><h2>This file could not be checked.</h2>
  <div class="pad"><p>No BAS figures were calculated. Fix the file, or name the quarter, and run the check again.</p>
  <ul class="clean">{items}</ul></div></section>
  <footer class="end"><p>Not tax advice. GST part of the BAS only. Do not email this folder.</p></footer>
</main>
"""
    css = (PACKAGE_TEMPLATES / "report.css").read_text(encoding="utf-8")
    template = Template((PACKAGE_TEMPLATES / "report.html.tpl").read_text(encoding="utf-8"))
    return template.substitute(
        title=html.escape(f"Could not check — {business}"),
        css=css,
        body=body,
        body_class="pooja" if theme == "pooja" else "",
    )


def format_local(value: str, timezone_name: str = "Australia/Sydney") -> str:
    """Show a saved UTC instant in local time, such as 13 November 2026, 11:44am AEDT."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value or "the previous run"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("Australia/Sydney")
    local = parsed.astimezone(zone)
    hour = local.strftime("%I").lstrip("0") or "12"
    clock = f"{hour}:{local.strftime('%M')}{local.strftime('%p').lower()}"
    label = local.tzname() or "AEST"
    return f"{local.day} {local.strftime('%B')} {local.year}, {clock} {label}"
