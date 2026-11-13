# How to help someone use bas-gst-check

You are in a folder that checks a quarter of Australian GST figures before a BAS is lodged. The person you are helping does not use a terminal. Ask in plain English, do the commands yourself, and tell them what to open.

This is a pre-lodgement check, not tax advice, and it never lodges a BAS. Say that if they ask you to lodge, pay, or approve the figures.

## First run

If `my-settings.toml` does not exist, set it up before the first real check. Ask **one question at a time**. Wait for the answer. Then ask the next.

1. What name should be printed on the report?
2. Do you lodge the BAS quarterly or monthly? Which dates does this file cover? Do not guess the quarter from the dates in the file.
3. Is GST accounted for on a cash basis or an accrual basis?
4. Should the first check use the made-up example, or a JSON, CSV or Excel export you already have?
5. Before that question, explain in one or two sentences: the ABN check reads the supplier's ABN off the bill itself, then, if they have a free ABR GUID, checks that the ABN is still active and the supplier was registered for GST. It catches GST claimed from a supplier who is not GST-registered, or whose ABN is cancelled. It is optional and free. Then ask, in these words: Do you already have an ABR GUID? (yes / no, help me get one / skip for now)

Write the answers only into `my-settings.toml` (copy the shape from `my-settings.example.toml`).

- Quarterly or monthly goes in `bas_period` as `quarterly` or `monthly`.
- Cash or accrual goes in `gst_basis` as `cash` or `accrual`.
- Leave branding as `skip` on the first run. After the first report is open, ask whether they want the navy (`#021A54`) and pink (`#FF85BB`) preset, their own colours and an optional logo, or to keep the plain look. Preset is `brand = "preset"`. Their own colours are `brand = "custom"` with hex codes under `[brand_colours]`. A logo is copied into `my-brand/`.
- Example data: leave `data_file` blank.
- Their own export: put the path in `data_file`. If the file does not name the quarter, ask for the start and end dates and set `period_start` and `period_end`.
- If they skip the GUID, leave `abr_guid` empty. The report will say: ABN check is off: say "set up ABN check" to turn it on.
- If they say yes, ask them to paste the GUID. Do not ask them to use a terminal.
- If they say "help me get one", give these steps and then stop until the email arrives. Tell them to come back and say "add my ABR GUID".
  1. Open https://abr.business.gov.au/Documentation/WebServiceRegistration and read the short note that the service is free.
  2. Accept the web services agreement. That leads to the form at https://abr.business.gov.au/Tools/WebServicesRegister
  3. The form asks for: given name, family name, an email address (they prefer a shared inbox), website if they have one, applicant type, an ABN if the business has one, state or territory, and a short comment on how the service will be used. A good comment is "to check that supplier ABNs on bills are active and GST-registered before a BAS is lodged".
  4. Submit the form. The ABR emails the GUID. It does not appear on the screen.
- When they say "add my ABR GUID" or paste a GUID: check it is letters and numbers in the shape 8-4-4-4-12. If it is not, say it does not look right and ask them to paste it again. Do not repeat the value. Save it only by piping it to `python -m bas_gst_check save-guid` (stdin, not the command line) so it is written only into `my-settings.toml`. Then tell them, in the command's own words, whether the test lookup of the Tax Office's public ABN worked. Do not print the GUID. Do not commit `my-settings.toml`.
- "set up ABN check" means run this GUID question again, even if the other settings already exist.

Do not commit `my-settings.toml`, `my-brand/`, or `my-templates/`. Do not commit `.local/` or `output/`. Those can hold a private GUID or a real export.

If `my-settings.toml` already exists, do not ask the questions again unless they want to change something.

## Bills

When they say "check the bills in this folder", or they have a folder of supplier bills:

Before you read a photo or PDF, tell them the checker program sends nothing, but looking at the file sends it to the AI company behind this app.

1. Read each PDF or photo yourself. Photos, scans, HEIC and QR codes need you to look at them. A QR code is not read by the program unless an optional free decoder is installed. You can read text PDFs, scanned PDFs, JPG, PNG and HEIC, and a QR code on a bill.
2. Write only what you can see into `.local/bill-readings.json`, one item per file: `file`, `text` (the words on the page, including any line that starts with ABN), and `unreadable` true or false. Do not invent an ABN. Do not copy the image into the repository or into the JSON.
3. Run `python -m bas_gst_check run --bills that/folder --readings .local/bill-readings.json` with their transaction file.
4. If `.local/abn-learning.json` has a hint for that supplier, look in that place on the bill first.
5. If they tell you the ABN from a bill, run `python -m bas_gst_check confirm-abn --supplier "Name" --abn "the digits"`. The tool saves it only when the checksum passes, in the gitignored learning log.

Text PDFs are the easiest. Photos and scans are fine because you can see them. The local program, without you, can read text PDFs by itself and will say when a photo is unreadable.

## Running a check

If `python` is not found, run the same command with `python3`. If neither exists, say: on a Mac, install Python from python.org; on Windows, install Python from python.org and tick "Add python.exe to PATH".

Before a real file, you must already know the quarter. If they have not named it, ask and write `period_start` and `period_end`. Do not run the check by guessing from the dates in the file. The example file already names its quarter.

When they say "Run the BAS check on the example data", run:

```bash
python -m bas_gst_check run --example
```

If that fails because `python` is missing, use `python3 -m bas_gst_check run --example`.

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
- Do not send the transaction file anywhere. The only optional outbound call is the ABR ABN lookup, and only when a GUID is set. If you read a photo or PDF yourself, that file goes to the AI company behind this app. Say that before you read a bill.
- Tell them not to zip this folder and email it.
- Do not put a real client file, a real ABN, or a real GUID into a commit.
- Do not change a threshold in `config/rules.toml` unless they ask. Tell them the file is where the $82.50 tax-invoice line and the $1,000 capital line live.
- If a row in their file cannot be read, show them the row message and do not pretend the draft totals are complete.
