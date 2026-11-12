"""Write the fictional Fennel Street Workshop quarter.

Every supplier ABN fails the ABN checksum on purpose. Nothing here is a real
business, a real person, or a real ABN.
"""

from __future__ import annotations

import csv
import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# The example builder is a script, so the repo root is not on sys.path until added.
sys.path.insert(0, str(ROOT))

from bas_gst_check.abn import abn_is_valid
ACTIVE = "11111111111"
CANCELLED = "22222222222"
NOT_GST = "33333333333"
NOT_FOUND = "44444444444"

# Contacts are invented trading names, not people.
SALES = "Sales"
RENT = "Sable Commercial"
SOFTWARE = "Kindling Software"
POWER = "Southbend Power"
PHONE = "Copperline Telecom"
INSURER = "Nettle Insurance"
FUEL = "Bramble Fuel"
ACCOUNTANT = "Fathom Accounting"
REPAIRS = "Cinder Repairs"
ADS = "Loom Advertising"
COURIER = "Parcel Counter"
STATIONERY = "Lumen Stationery"
EQUIPMENT = "Harrow Equipment"
BANK = "Riverbend Bank"
GROCER = "Creek Road Grocer"
REGISTER = "Companies Register"
WAGES = "Staff Wages"
SUPER = "Staff Super"


def main() -> None:
    for abn in (ACTIVE, CANCELLED, NOT_GST, NOT_FOUND):
        if abn_is_valid(abn):
            raise SystemExit(f"{abn} is a valid ABN and cannot be used as fiction")
    rows = _rows()
    if not 60 <= len(rows) <= 80:
        raise SystemExit(f"expected 60 to 80 transactions, got {len(rows)}")
    payload = {
        "business_name": "Fennel Street Workshop",
        "period_start": "2026-07-01",
        "period_end": "2026-09-30",
        "gst_basis": "accrual",
        "fictional": True,
        "note": "Made-up example. Not a real business, not real contacts, and the ABNs fail the checksum.",
        "transactions": rows,
    }
    json_path = ROOT / "examples" / "fennel-street-workshop.json"
    csv_path = ROOT / "examples" / "fennel-street-workshop.csv"
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "date",
                "type",
                "contact",
                "description",
                "account",
                "net_amount",
                "gst_amount",
                "tax_code",
                "supplier_abn",
                "reference",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in writer.fieldnames})
    print(f"Wrote {len(rows)} transactions to {json_path.name} and {csv_path.name}")


def _rows() -> list[dict[str, str]]:
    counter = {"n": 2400}

    def ref() -> str:
        counter["n"] += 1
        return f"INV-{counter['n']}"

    def add(date, side, contact, description, account, net, code, gst=None, abn=""):
        net_amount = Decimal(net)
        if gst is None:
            taxable = code in {"GST on Income", "GST on Expenses", "GST on Capital"}
            gst_amount = (net_amount / Decimal(10)).quantize(Decimal("0.01")) if taxable else Decimal("0.00")
        else:
            gst_amount = Decimal(gst).quantize(Decimal("0.01"))
        row = {
            "date": date,
            "type": side,
            "contact": contact,
            "description": description,
            "account": account,
            "net_amount": f"{net_amount:.2f}",
            "gst_amount": f"{gst_amount:.2f}",
            "tax_code": code,
            "reference": ref(),
        }
        if abn:
            row["supplier_abn"] = abn
        return row

    sale = "sale"
    buy = "purchase"
    gst_in = "GST on Income"
    gst_out = "GST on Expenses"
    free = "GST Free"
    excluded = "BAS Excluded"
    taxed = "Input Taxed"

    rows = [
        add("2026-07-03", sale, "Plover Shire Hall", "Wayfinding concept", SALES, "1800", gst_in),
        add("2026-07-10", sale, "Brindle Archive", "Identity system", SALES, "2400", gst_in),
        add("2026-07-16", sale, "Lowtide Gallery", "Exhibition graphics", SALES, "960", gst_in),
        add("2026-07-22", sale, "Amberline Publishing", "Cover series", SALES, "1500", gst_in),
        add("2026-07-29", sale, "Mallow Civic Hall", "Annual report design", SALES, "3200", gst_in),
        add("2026-08-05", sale, "Cobble Press", "Poster set", SALES, "640", gst_in),
        add("2026-08-12", sale, "Otterlane Rooms", "Menu suite", SALES, "880", gst_in),
        add("2026-08-19", sale, "Quince Market", "Stall signage", SALES, "420", gst_in),
        add("2026-08-26", sale, "Driftwood Hire", "Fleet decals", SALES, "1100", gst_in),
        add("2026-09-02", sale, "Paperwharf Rooms", "Room guide", SALES, "760", gst_in),
        add("2026-09-09", sale, "Plover Shire Hall", "Phase two revisions", SALES, "540", gst_in),
        add("2026-09-16", sale, "Brindle Archive", "Reprint layout", SALES, "300", gst_in),
        add("2026-07-08", sale, "Amberline Publishing", "Export of printed posters", SALES, "600", free),
        add("2026-09-30", sale, BANK, "Interest received", "Interest income", "18.40", taxed),
        add("2026-08-14", sale, "Cobble Press", "Credit for unused posters", SALES, "-200", gst_in),
        add("2026-07-21", sale, "Mallow Civic Hall", "Brand workshop", SALES, "2000", gst_in, gst="100"),
        add("2026-08-03", sale, BANK, "Interest received", "Interest income", "40", gst_in),
        add("2026-09-04", sale, "Plover Shire Hall", "Strategy intensive", SALES, "1500", excluded),
        add("2026-06-18", sale, "Lowtide Gallery", "June leftover invoice", SALES, "500", gst_in),
        add("2026-10-06", sale, "Amberline Publishing", "October deposit", SALES, "250", gst_in),
        add("2026-07-01", buy, RENT, "Studio rent", "Rent", "2200", gst_out, abn=ACTIVE),
        add("2026-07-02", buy, SOFTWARE, "Design software subscription", "Software", "90", gst_out, abn=ACTIVE),
        add("2026-07-06", buy, POWER, "Electricity", "Electricity", "310", gst_out, abn=ACTIVE),
        add("2026-07-06", buy, PHONE, "Studio internet", "Telephone", "120", gst_out, abn=ACTIVE),
        add("2026-07-07", buy, INSURER, "Studio cover", "Insurance", "430", gst_out, abn=ACTIVE),
        add("2026-07-09", buy, FUEL, "Van fuel", "Motor vehicle expenses", "85", gst_out, abn=ACTIVE),
        add("2026-07-13", buy, ACCOUNTANT, "Quarter prep", "Accounting fees", "600", gst_out, abn=ACTIVE),
        add("2026-07-15", buy, REPAIRS, "Door repair", "Repairs", "275", gst_out, abn=ACTIVE),
        add("2026-07-20", buy, ADS, "Poster boost", "Advertising", "360", gst_out, abn=ACTIVE),
        add("2026-07-24", buy, COURIER, "Sample delivery", "Courier", "48", gst_out, abn=ACTIVE),
        add("2026-07-28", buy, STATIONERY, "Copy paper", "Office expenses", "75", gst_out, abn=ACTIVE),
        add("2026-08-04", buy, STATIONERY, "Notebooks", "Office expenses", "40", gst_out, abn=ACTIVE),
        add("2026-08-07", buy, RENT, "Studio rent", "Rent", "2200", gst_out, abn=ACTIVE),
        add("2026-08-11", buy, POWER, "Electricity", "Electricity", "280", gst_out, abn=ACTIVE),
        add("2026-08-18", buy, ACCOUNTANT, "Bookkeeping", "Accounting fees", "450", gst_out, abn=ACTIVE),
        add("2026-08-21", buy, REPAIRS, "Window seal", "Repairs", "190", gst_out, abn=ACTIVE),
        add("2026-08-25", buy, ADS, "Magazine listing", "Advertising", "210", gst_out, abn=ACTIVE),
        add("2026-09-01", buy, RENT, "Studio rent", "Rent", "2200", gst_out, abn=ACTIVE),
        add("2026-09-03", buy, PHONE, "Studio internet", "Telephone", "120", gst_out, abn=ACTIVE),
        add("2026-09-08", buy, FUEL, "Van fuel", "Motor vehicle expenses", "96", gst_out, abn=ACTIVE),
        add("2026-09-11", buy, COURIER, "Poster tubes", "Courier", "70", gst_out),
        add("2026-09-15", buy, STATIONERY, "Ink cartridges", "Office expenses", "66", gst_out, abn=ACTIVE),
        add("2026-07-30", buy, EQUIPMENT, "Laptop for the studio", "Computer equipment", "1800", gst_out, abn=ACTIVE),
        add("2026-08-13", buy, STATIONERY, "Studio stool", "Office expenses", "540", gst_out, abn=ACTIVE),
        add("2026-07-31", buy, BANK, "Account keeping fee", "Bank fees", "15", taxed),
        add("2026-07-15", buy, WAGES, "Fortnightly wages", "Wages", "3200", excluded),
        add("2026-07-29", buy, WAGES, "Fortnightly wages", "Wages", "3200", excluded),
        add("2026-08-12", buy, WAGES, "Fortnightly wages", "Wages", "3200", excluded),
        add("2026-08-26", buy, WAGES, "Fortnightly wages", "Wages", "3200", excluded),
        add("2026-09-09", buy, WAGES, "Fortnightly wages", "Wages", "3200", excluded),
        add("2026-09-23", buy, WAGES, "Fortnightly wages", "Wages", "3200", excluded),
        add("2026-07-28", buy, SUPER, "Superannuation contribution", "Superannuation", "304", excluded),
        add("2026-08-28", buy, SUPER, "Superannuation contribution", "Superannuation", "304", excluded),
        add("2026-09-28", buy, SUPER, "Superannuation contribution", "Superannuation", "304", excluded),
        add("2026-09-18", buy, REGISTER, "ASIC annual review fee", "Filing fees", "310", free),
        add("2026-08-02", buy, GROCER, "Plain flour and white rice", "Staff amenities", "36", free),
        add("2026-08-31", buy, BANK, "Account keeping fee", "Bank fees", "22", gst_out, abn=ACTIVE),
        add("2026-09-23", buy, WAGES, "Back pay wages", "Wages", "800", gst_out, abn=ACTIVE),
        add("2026-08-28", buy, SUPER, "Superannuation contribution", "Superannuation", "200", gst_out, abn=ACTIVE),
        add("2026-07-14", buy, REGISTER, "ASIC annual review fee", "Filing fees", "200", gst_out, abn=ACTIVE),
        add("2026-08-16", buy, GROCER, "Plain milk and bread", "Staff amenities", "20", gst_out, abn=ACTIVE),
        add("2026-09-02", buy, SOFTWARE, "Design software subscription", "Software", "90", free),
        add("2026-09-22", buy, RENT, "Storage rent", "Rent", "400", free),
        add("2026-08-20", buy, ADS, "Online ads", "Advertising", "250", excluded),
        add("2026-07-11", buy, STATIONERY, "Copy paper", "Office expenses", "50", gst_out, abn=ACTIVE),
        add("2026-06-28", buy, STATIONERY, "June paper", "Office expenses", "30", gst_out, abn=ACTIVE),
        add("2026-08-09", buy, REPAIRS, "Lock replacement", "Repairs", "500", gst_out, gst="20", abn=ACTIVE),
        add("2026-09-07", buy, EQUIPMENT, "Studio camera", "General expenses", "1600", gst_out, abn=ACTIVE),
        add("2026-09-12", buy, COURIER, "Large crate delivery", "Courier", "180", gst_out),
        add("2026-07-27", buy, EQUIPMENT, "Drawing table", "General expenses", "300", gst_out, abn=CANCELLED),
        add("2026-08-06", buy, SOFTWARE, "Plugin licence", "Software", "150", gst_out, abn=NOT_GST),
        add("2026-08-17", buy, "Bluegum Hosting", "Site hosting", "Software", "140", gst_out, abn=NOT_FOUND),
    ]
    twin = next(row for row in rows if row["date"] == "2026-07-11" and row["description"] == "Copy paper")
    rows.append(dict(twin))
    return rows


if __name__ == "__main__":
    main()
