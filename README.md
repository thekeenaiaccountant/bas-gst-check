# bas-gst-check

Check a quarter of GST figures before the BAS is lodged, and see the likely mistakes.

![Draft BAS report for the fictional example, using the navy and pink preset](docs/screenshot.png)

![A short scroll through the same report](docs/walkthrough.gif)

The picture uses the navy and pink preset. Until you choose a brand, the report uses the paper-and-ink default. **Every name, amount and ABN in the example is made up.** Fennel Street Workshop is not a real business.

This copy is private for now. Do not publish the repository. The licence, when you do share it, is MIT.

## Start here

Open this folder in Claude Code or Codex. You do not need the terminal. Type:

```text
Set up BAS GST check
```

It asks one question at a time: the business name, quarterly or monthly, cash or accrual, branding (the navy `#021A54` and pink `#FF85BB` preset, your own colours and logo, or skip), whether to use the example or your own export, and whether you have an ABR GUID. You can skip the GUID.

Then type:

```text
Run the BAS check on the example data
```

Open `output/bas-gst-check.html`. The same flagged lines are in `output/flagged-items.csv` if you want them in a spreadsheet.

When a line is dealt with, type:

```text
Mark flag F-01 as fixed. Note: recoded the bank fee and set the GST to zero.
```

or:

```text
Mark flag F-04 as ignored. Note: tax invoice is on file and the GST is correct.
```

Use the id from the report you are looking at. The next run shows what changed, and it repeats your note. Notes stay in a folder on this computer (`.local/`). Nothing in the transaction file is uploaded.

## What the report shows

- **G1** total sales, **1A** GST on sales, **1B** GST on purchases, and whether the net GST is payable or refundable.
- **G10** and **G11**, so capital purchases are visible. Simpler BAS (GST turnover under $10 million) does not lodge those two labels, but the split still keeps the file tidy.
- Each flagged line, in plain English: why it was flagged, and a suggested fix.
- A **since last time** panel, once you have run it more than once.
- Your fixed and ignored notes.
- Next steps, and the ATO pages the rules come from.

The draft uses the amounts in the file. It does not silently rewrite them. GST adjustments such as bad debts or private use are not included. Cash basis means the file should be amounts you received or paid in the period. Accrual basis means invoices and bills for the period. The tool does not invent a second date.

## Your file

Use JSON or CSV. Each row needs a date, whether it is a sale or a purchase, a contact, a description, an account, a net amount, a GST amount, and a tax code. A supplier ABN column is optional and is used only by the ABN check.

Tax codes it understands: GST on Income, GST on Expenses, GST on Capital, GST Free, BAS Excluded, Input Taxed.

The made-up quarter is `examples/fennel-street-workshop.json` (1 July 2026 to 30 September 2026). `examples/fennel-street-workshop.csv` is the same quarter. The JSON file already names the period. For a CSV, say which dates the file covers.

## What each check means

**GST is not one-eleventh.** On a taxable line, GST should be one-eleventh of the GST-inclusive amount (net plus GST), rounded to the nearest cent. The review tolerance is in `config/rules.toml` (five cents unless you change it). A GST amount on a GST-free, input-taxed or BAS Excluded code is flagged too.

**GST on things that usually have none.** Bank account fees, interest, wages, super, ASIC annual review fees, and many basic foods (plain milk, bread, flour, uncooked rice) usually should not carry GST. Prepared meals often should. The note tells you which group matched. This is a prompt to look, not a ruling.

**No GST on a usually taxable expense.** Rent, software, advertising, electricity and similar purchases are often taxable. The flag appears when the code says GST-free or input-taxed. It is correct if the supplier is not registered for GST.

**BAS Excluded, but it looks like a real sale or expense.** BAS Excluded drops the line off the BAS. That fits wages, super, drawings and transfers. It does not fit a workshop fee or a toner purchase.

**Possible duplicate.** Same date, contact, description and amounts as another row. Two genuine supplies can look like this. The suggestion is to delete only the extra copy.

**Outside the period.** The date is not inside the quarter or month you named. Cash basis cares about when money moved. Accrual basis cares about the invoice or bill date, or the payment if that came first.

**Tax invoice to have on file.** A purchase that claims a GST credit and costs **more than $82.50 including GST**. $82.50 exactly does not need a tax invoice; a receipt is enough. The tool cannot see your documents. It is a reminder list, not proof that the invoice is missing.

**Capital purchase, G10 or G11.** Equipment and similar assets over the threshold (default $1,000 including GST) that are sitting on an expense account. The ATO expects capital items costing more than $1,000 at G10 when capital purchases are not already recorded separately. Repairs, hires and leases are not capital. The draft leaves the line where the account put it and asks you to move it if it really is an asset.

**No supplier ABN.** The purchase claims GST, it is over the tax-invoice threshold, and the file has no supplier ABN. A tax invoice at that amount has to show one.

**ABN lookup** (only when a GUID is set). For purchases that claim GST and are over the threshold, the tool asks the free ABR service about the supplier ABN. It flags an ABN that is not found, an ABN that was already cancelled on the purchase date, and an entity that was not registered for GST on that date. A timeout is reported as "could not check", and the line is not treated as a failed ABN. Saved answers sit in `.local/` so the same ABN is not looked up on every run.

A tax code the tool does not recognise is left out of the draft totals and listed, so a strange code cannot quietly disappear.

## Optional: ABN check

The supplier check is off until you add a GUID. Register a free one with the Australian Business Register: [Web services registration](https://abr.business.gov.au/Documentation/WebServiceRegistration). They email the GUID to you. In Claude Code or Codex, type:

```text
I have an ABR GUID. Save it for the ABN check.
```

You can skip this. With no GUID, the report says the lookup was not run, and it still lists GST purchases that have no ABN in the file.

The GUID belongs only in `my-settings.toml` (or in an `ABR_GUID` environment variable). That settings file is gitignored. Do not paste the GUID into the example file, the README, or a commit. The example ABNs are fictional and fail the ABN checksum, so a live lookup of the example will not find a real supplier. The tests use saved fictional replies instead of calling the ABR.

## Not tax advice

This is a pre-lodgement checker. It is not tax advice, and it does not lodge or pay a BAS. Confirm the figures with a registered BAS or tax agent before you lodge.

The dollar thresholds live in [`config/rules.toml`](config/rules.toml). The report links to the ATO pages used for G1, 1A, 1B, G10, G11, tax invoices, GST-free supplies, and cash versus accrual accounting.

## For developers

Python 3.11 or newer. The check itself uses the standard library.

```bash
pip install -e ".[dev]"
python -m pytest
python -m bas_gst_check run --example
python scripts/check_public_safe.py
gitleaks detect --source . --config .gitleaks.toml --no-banner
```

`my-settings.toml`, `my-brand/` and `my-templates/` override the defaults and are not committed. A full HTML shell can be replaced with `my-templates/report.html.tpl` (`$title`, `$css`, `$body`). Extra CSS goes in `my-templates/extra.css`.

## Licence

MIT. Copyright (c) 2026 Pooja K. See [LICENSE](LICENSE).
