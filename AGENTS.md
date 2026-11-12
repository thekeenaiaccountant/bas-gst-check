# How to help someone use bas-gst-check

You are in a folder that checks a quarter of Australian GST figures before a BAS is lodged. The person you are helping does not use a terminal. Ask in plain English, do the commands yourself, and tell them what to open.

This is a pre-lodgement check, not tax advice, and it never lodges a BAS. Say that if they ask you to lodge, pay, or approve the figures.

## First run

If `my-settings.toml` does not exist, set it up before the first real check. Ask **one question at a time**. Wait for the answer. Then ask the next.

1. What name should be printed on the report?
2. Do you lodge the BAS quarterly or monthly?
3. Is GST accounted for on a cash basis or an accrual basis?
4. For the colours, do you want the navy (`#021A54`) and pink (`#FF85BB`) preset, your own colours and an optional logo, or no special branding?
5. Should the first check use the made-up example, or a JSON or CSV export you already have?
6. Do you have an ABR GUID? You can skip this. It is a free key from the Australian Business Register that lets the tool look up supplier ABNs. People register at https://abr.business.gov.au/Documentation/WebServiceRegistration

Write the answers only into `my-settings.toml` (copy the shape from `my-settings.example.toml`).

- Quarterly or monthly goes in `bas_period` as `quarterly` or `monthly`.
- Cash or accrual goes in `gst_basis` as `cash` or `accrual`.
- Preset branding: `brand = "preset"`.
- Their own colours: `brand = "custom"`, then ask for the two hex codes and write them under `[brand_colours]`. If they have a logo, copy the image into `my-brand/` and set `logo` to the file name. Ask about the logo only after they have chosen their own colours.
- No branding: `brand = "skip"`.
- Example data: leave `data_file` blank.
- Their own export: put the path in `data_file`. If the file does not name the quarter, ask for the start and end dates and set `period_start` and `period_end`.
- If they skip the GUID, leave `abr_guid` empty.
- If they give you a GUID, store it only as `abr_guid` in `my-settings.toml`. Do not repeat the GUID in the chat, the report, a commit, the README, or any other file.

Do not commit `my-settings.toml`, `my-brand/`, or `my-templates/`. Do not commit `.local/` or `output/`. Those can hold a private GUID or a real export.

If `my-settings.toml` already exists, do not ask the questions again unless they want to change something.

## Running a check

When they say "Run the BAS check on the example data", run:

```bash
python -m bas_gst_check run --example
```

When they want their own file, run:

```bash
python -m bas_gst_check run path/to/their-file.csv
```

If the command is not found, install once with:

```bash
pip install -e ".[dev]"
```

Tell them the HTML report is `output/bas-gst-check.html` and the spreadsheet of flagged lines is `output/flagged-items.csv`. Offer to open the report. Summarise the draft G1, 1A, 1B and whether the net is payable or refundable, then the lines that need a human. Do not invent a different total.

The example business, contacts, amounts and ABNs are fictional. Say that. A live ABR lookup of the example will not find those ABNs, because they are not real. The automated tests replay saved fictional answers instead.

## Notes they can keep

When they say "Mark flag F-01 as fixed" and give a note, run:

```bash
python -m bas_gst_check note F-01 --status fixed --note "their note"
```

Use `ignored` or `open` the same way. The id has to be the one in the latest report. The note is stored in `.local/` on this computer and shown on the next run. Nothing is uploaded.

## Rules you do not break

- Do not lodge, pay, or mark the BAS approved.
- Do not send the transaction file anywhere. The only optional outbound call is the ABR ABN lookup, and only when a GUID is set.
- Do not put a real client file, a real ABN, or a real GUID into a commit.
- Do not change a threshold in `config/rules.toml` unless they ask. Tell them the file is where the $82.50 tax-invoice line and the $1,000 capital line live.
- If a row in their file cannot be read, show them the row message and do not pretend the draft totals are complete.
