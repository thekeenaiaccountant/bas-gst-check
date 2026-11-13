"""Self-contained HTML report and CSV of flagged lines."""

from __future__ import annotations

import csv
import html
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pathlib import Path
from string import Template

from bas_gst_check.abr import AbrOutcome
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
    open_errors, fixed_still, ignored, invoices = _buckets(flags, notes)
    error_count = len(open_errors) + len(fixed_still)
    parts = [
        '<main class="wrap">',
        _header(business, period, basis, bas_period, logo_html),
        _disclaimer(),
    ]
    if fictional:
        parts.append(
            '<p class="example-banner">These figures are made-up example data for a fictional business. They are not a real client and not a real BAS.</p>'
        )
    if period_warning:
        parts.append(f'<p class="example-banner">{html.escape(period_warning)}</p>')
    if summary.left_out:
        parts.append(
            '<section class="disclaimer warn"><strong>These draft figures are incomplete.</strong> '
            f"<p>{summary.left_out} line{'s were' if summary.left_out != 1 else ' was'} left out because the tax code "
            "or the sale/purchase side was not recognised. This is not a nil BAS. "
            "Do not lodge these numbers until those lines are coded.</p></section>"
        )
    parts.append(_figures(summary, basis))
    parts.append(_split(summary))
    parts.append("<h2>Since last time</h2>")
    parts.append(_since(comparison, timezone_name))
    parts.append("<h2>Supplier ABN check</h2>")
    parts.append(_abr_panel(abr))
    parts.append(_abn_help(bills_provided))
    parts.append("<h2>What I found hard this time</h2>")
    parts.append(_hard_panel(hard_lines))
    parts.append(f"<h2>{error_count} line{'s' if error_count != 1 else ''} to fix before lodgement</h2>")
    if not flags:
        parts.append(
            '<section class="panel"><p>Nothing in this file was flagged. The draft figures are only as good as the export. '
            "Confirm them with a registered BAS or tax agent. This check does not see adjustments, private-use splits, or documents that are not in the file.</p></section>"
        )
    else:
        if fixed_still:
            parts.append("<h3>Marked fixed, still in the file</h3>")
            parts.extend(_card(flag, notes.get(flag.fingerprint)) for flag in fixed_still)
        if open_errors:
            parts.extend(_card(flag, notes.get(flag.fingerprint)) for flag in open_errors)
        if not open_errors and not fixed_still:
            parts.append('<section class="panel"><p>No likely mistakes are still open. Review items, if any, are below.</p></section>')
        parts.append(_invoice_section(invoices, notes))
        if ignored:
            parts.append(f"<h2>Ignored ({len(ignored)})</h2>")
            parts.extend(_card(flag, notes.get(flag.fingerprint)) for flag in ignored)
    parts.append("<h2>Next steps</h2>")
    parts.append(_next(flags, notes, abr))
    parts.append("<h2>How the draft was added up</h2>")
    parts.append(_method(summary, rules, basis))
    parts.append("<h2>Sources</h2>")
    parts.append(_sources())
    parts.append(
        '<footer class="end"><p>This checker sends nothing. It keeps the run, your notes and any ABR answers in a local folder. '
        "A photo or PDF that Claude or Codex reads is sent to that AI company. "
        "Do not zip this folder and email it. It does not lodge a BAS.</p></footer>"
    )
    parts.append("</main>")
    return "\n".join(parts)


def _buckets(
    flags: list[Flag], notes: dict[str, Note]
) -> tuple[list[Flag], list[Flag], list[Flag], list[Flag]]:
    open_errors: list[Flag] = []
    fixed_still: list[Flag] = []
    ignored: list[Flag] = []
    invoices: list[Flag] = []
    for flag in flags:
        note = notes.get(flag.fingerprint)
        if note and note.status == "ignored":
            ignored.append(flag)
            continue
        if note and note.status == "fixed":
            fixed_still.append(flag)
            continue
        if flag.code == "tax_invoice":
            invoices.append(flag)
            continue
        open_errors.append(flag)
    return open_errors, fixed_still, ignored, invoices


def _header(business: str, period: Period, basis: str, bas_period: str, logo_html: str) -> str:
    basis_label = "Cash" if basis == "cash" else "Accrual"
    rhythm = "Quarterly" if bas_period == "quarterly" else "Monthly"
    return f"""
<header class="top">
  <div>
    {logo_html}
    <p class="eyebrow"><span class="mark">GST</span> part of the BAS only</p>
    <h1>{html.escape(business)}</h1>
    <p class="lede">{html.escape(period_label(period.start, period.end))} · {rhythm} · {basis_label} · Prepared on this computer</p>
  </div>
  <div class="stamp">Check<br>only<br>not lodged</div>
</header>
"""


def _disclaimer() -> str:
    return (
        '<section class="disclaimer"><strong>Not tax advice.</strong> '
        "<p>This is a pre-lodgement checker for the GST part of the BAS only. It does not lodge, pay, or approve a BAS. "
        "Confirm the figures with a registered BAS or tax agent before you lodge. "
        "Do not zip this folder and email it. It can hold your file, your GUID and notes that should stay on this computer.</p></section>"
    )


def _figures(summary: Summary, basis: str) -> str:
    unusable = summary.left_out and summary.g1 == 0 and summary.gst_on_sales == 0 and summary.gst_on_purchases == 0
    if unusable:
        position = "Not a usable BAS"
        net_class = "payable"
    else:
        position = {"payable": "Payable", "refundable": "Refundable", "nil": "Nil"}[summary.position]
        net_class = summary.position
    net = money_text(abs(summary.net)) if summary.position != "nil" and not unusable else money_text(summary.net)
    basis_note = (
        "Cash basis: only money received or paid in this period belongs here."
        if basis == "cash"
        else "Accrual basis: invoices and bills for this period belong here."
    )
    return f"""
<section class="figures" aria-label="Draft BAS summary">
  <article class="figure"><span>G1 total sales</span><strong>{money_text(summary.g1)}</strong><em>GST-inclusive</em></article>
  <article class="figure"><span>1A GST on sales</span><strong>{money_text(summary.gst_on_sales)}</strong><em>As recorded</em></article>
  <article class="figure"><span>1B GST on purchases</span><strong>{money_text(summary.gst_on_purchases)}</strong><em>As recorded</em></article>
  <article class="figure {net_class}"><span>Net GST</span><strong>{net}</strong><em>{position}</em></article>
</section>
<p class="example-banner">Do not copy these onto the BAS until the red lines are cleared. {html.escape(basis_note)} These totals are only right if the file is already the list you lodge on that basis.</p>
"""


def _split(summary: Summary) -> str:
    return f"""
<section class="split">
  <div><span>G10 capital purchases</span><strong>{money_text(summary.g10)}</strong><em>From capital accounts in the file</em></div>
  <div><span>G11 non-capital purchases</span><strong>{money_text(summary.g11)}</strong><em>Other purchases, excluding BAS Excluded</em></div>
</section>
"""


def _since(comparison: Comparison, timezone_name: str) -> str:
    if not comparison.has_previous:
        return (
            '<section class="panel"><p>This is the first run saved on this computer. '
            "The next run will show what moved in the draft figures and which flags disappeared.</p></section>"
        )
    bits = []
    labels = {
        "g1": "G1",
        "gst_on_sales": "1A",
        "gst_on_purchases": "1B",
        "net": "Net GST",
    }
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
        '<section class="panel">'
        f"<p>Compared with the run on {html.escape(format_local(comparison.previous_at, timezone_name))}.</p>"
        f"<p class='delta'>{html.escape('; '.join(bits))}.</p>"
        f"<p>{new_count} new flag{'s' if new_count != 1 else ''}. "
        f"{comparison.still_open} still open from last time. "
        f"{len(comparison.cleared_labels)} cleared.</p>"
        f"{cleared}"
        "</section>"
    )


def _abn_help(bills_provided: bool) -> str:
    where = (
        "A bills folder was included in this run."
        if bills_provided
        else "No bills folder was included. Say where the bills are saved, for example 'check the bills in this folder'."
    )
    return (
        '<section class="panel"><p><strong>How supplier ABNs are read.</strong> '
        "The number has to be on the bill, next to the word ABN. Text PDFs work best on this computer. "
        "Photos, scans and HEIC files are not read here. Claude or Codex has to look at them, and that sends the picture to that AI company. "
        "A QR code needs the app to read it, or an optional free decoder on this computer. "
        "A number is never guessed. If you have saved a free ABR GUID, that ABN is then checked only to see "
        "if it is active and the supplier was registered for GST. "
        f"{html.escape(where)} "
        'Say "set up ABN check" any time to turn the ABR part on or off.</p></section>'
    )


def _hard_panel(lines: list[str]) -> str:
    if not lines:
        return '<section class="panel"><p>Nothing was marked hard on this run.</p></section>'
    items = "".join(f"<li>{html.escape(line)}</li>" for line in lines[:12])
    return f'<section class="panel"><ul class="clean">{items}</ul></section>'


def _abr_panel(abr: AbrOutcome) -> str:
    notes = ""
    if abr.notes:
        items = "".join(
            f"<li>{html.escape(note.supplier_abn)} ({html.escape(note.contact)}): {html.escape(note.reason)}</li>"
            for note in abr.notes
        )
        notes = f"<ul class='clean'>{items}</ul>"
    return f'<section class="panel"><p>{html.escape(abr.message)}</p>{notes}</section>'


def _card(flag: Flag, note: Note | None) -> str:
    transaction = flag.transaction
    meta = _meta(transaction) if transaction else ""
    noted = ""
    if note:
        noted = (
            f'<p class="fix"><span class="chip note">{html.escape(note.status)}</span> '
            f"{html.escape(note.text) if note.text else 'No note was saved.'}</p>"
        )
    return f"""
<article class="card" id="{html.escape(flag.short_id)}">
  <header>
    <h3>{html.escape(flag.short_id)} · {html.escape(flag.title)}</h3>
    <span class="chip {html.escape(flag.severity)}">{html.escape(flag.severity)}</span>
  </header>
  {meta}
  <p class="why">{html.escape(flag.why)}</p>
  <p class="fix"><strong>Suggested fix.</strong> {html.escape(flag.fix)}</p>
  {noted}
  <p><a href="{html.escape(flag.source_url)}">{html.escape(flag.source_title)}</a></p>
</article>
"""


def _meta(transaction: Transaction) -> str:
    abn = transaction.supplier_abn or "—"
    reference = transaction.reference or "—"
    return (
        f'<p class="who">{html.escape(transaction.date.isoformat())} · {html.escape(transaction.contact)}'
        f" · {html.escape(transaction.description)}</p>"
        f'<p class="who quiet">{html.escape(transaction.account)} · {html.escape(transaction.tax_code_label)}'
        f" · Ref {html.escape(reference)} · ABN {html.escape(abn)}</p>"
        f'<p class="who"><strong>Net {money_text(transaction.net)}</strong>'
        f" · GST {money_text(transaction.gst)} · Inclusive {money_text(transaction.inclusive)}</p>"
    )


def _invoice_section(invoices: list[Flag], notes: dict[str, Note]) -> str:
    if not invoices:
        return ""
    rows = []
    for flag in invoices:
        transaction = flag.transaction
        if transaction is None:
            continue
        rows.append(
            "<tr>"
            f"<td>{html.escape(flag.short_id)}</td>"
            f"<td>{html.escape(transaction.date.isoformat())}</td>"
            f"<td>{html.escape(transaction.contact)}</td>"
            f"<td>{html.escape(transaction.description)}</td>"
            f"<td class='num'>{money_text(transaction.inclusive)}</td>"
            f"<td class='num'>{money_text(transaction.gst)}</td>"
            f"<td>{html.escape(transaction.supplier_abn or '—')}</td>"
            "</tr>"
        )
    table = (
        '<div class="table-wrap"><table><thead><tr>'
        "<th>Flag</th><th>Date</th><th>Contact</th><th>Description</th>"
        "<th class='num'>Inclusive</th><th class='num'>GST</th><th>ABN</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )
    sample = invoices[0]
    return (
        "<details>"
        f"<summary><h2>Tax invoices to have on file ({len(invoices)})</h2></summary>"
        '<section class="panel"><p>Each of these claims a GST credit above the tax-invoice threshold. '
        "The check cannot see the document. Confirm it is on file before the credit stays in 1B.</p>"
        f"<p>{html.escape(sample.why)}</p></section>"
        f"{table}"
        "</details>"
    )


def _next(flags: list[Flag], notes: dict[str, Note], abr: AbrOutcome) -> str:
    first = flags[0].short_id if flags else "F-01"
    steps = [
        "Work through the lines marked error. The draft totals follow the file as it is, so a fix in the books will change G1, 1A or 1B on the next run.",
        "For the tax-invoice list, tick off the documents. If one is missing, take that GST out of 1B until it arrives.",
        f"When a line is dealt with, say: Mark flag {first} as fixed. Note: and a short reason. Ignored lines come back next time with your note attached.",
        "Ask a registered BAS or tax agent to confirm the figures. This report is not the lodgement.",
    ]
    if abr.mode == "off":
        steps.insert(2, 'ABN check is off: say "set up ABN check" to turn it on.')
    items = "".join(f"<li>{html.escape(step)}</li>" for step in steps)
    return f'<section class="panel next"><ol>{items}</ol></section>'


def _method(summary: Summary, rules: Rules, basis: str) -> str:
    basis_text = (
        "Cash basis: this file should contain only amounts you received or paid in the period."
        if basis == "cash"
        else "Accrual basis: this file should contain invoices and bills for the period (and payments, where they came first)."
    )
    return f"""
<section class="panel">
  <p>{html.escape(basis_text)} The tool does not rebuild cash or accrual from a second date. It checks the dates that are in the file.</p>
  <p>G1 is the GST-inclusive total of sales that are not BAS Excluded (taxable, GST-free and input-taxed). That matches the calculation worksheet method, which includes GST in G1. 1A is the GST recorded on taxable sales. 1B is the GST recorded on taxable purchases. Net GST is 1A minus 1B.</p>
  <p>G10 is purchases on a capital or asset account, including a line coded GST on Capital. Everything else that is not BAS Excluded sits in G11. A capital-looking expense over {money_text(rules.capital_threshold)} is flagged, not silently moved. Simpler BAS, for GST turnover under $10 million, lodges G1, 1A and 1B only.</p>
  <p>GST adjustments (bad debts, private use, annual apportionment) are not in this draft. {summary.left_out} line{'s were' if summary.left_out != 1 else ' was'} left out because the sale/purchase side or the tax code could not be read. Rounding tolerance for the one-eleventh check is {money_text(rules.tolerance)}.</p>
</section>
"""


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
  <p class="eyebrow"><span class="mark">GST</span> part of the BAS only</p>
  <h1>{html.escape(business)}</h1>
  <section class="disclaimer error"><strong>This file could not be checked.</strong>
  <p>No BAS figures were calculated. Fix the file, or name the quarter, and run the check again.</p>
  <ul class="clean">{items}</ul></section>
  <p>Do not copy anything from an older report onto the BAS. This checker sends nothing. Do not zip this folder and email it.</p>
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
