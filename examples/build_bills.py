"""Write the made-up supplier bills used by the example.

The ABNs are listed in fictional-abns.txt. They pass the checksum and are not
real businesses.
"""

from __future__ import annotations

import json
import struct
import zlib
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "bills"


def main() -> None:
    numbers = [
        line.strip()
        for line in (ROOT / "fictional-abns.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    sable, bluegum, kindling, nobody = numbers
    _pdf(ROOT / "sable-rent.pdf", [
        "MADE UP EXAMPLE BILL. Not a real business.",
        "From: Sable Commercial",
        "Invoice date: 2026-07-01",
        "Description: Studio rent",
        "Total: 2420.00",
        "GST: 220.00",
        f"ABN: {_spaced(sable)}",
    ])
    _pdf(ROOT / "bluegum-hosting.pdf", [
        "MADE UP EXAMPLE BILL. Not a real business.",
        "From: Bluegum Hosting",
        "Invoice date: 2026-08-17",
        "Description: Site hosting",
        "Total: 154.00",
        "GST: 14.00",
        f"ABN: {_spaced(bluegum)}",
    ])
    _pdf(ROOT / "kindling-plugin.pdf", [
        "MADE UP EXAMPLE BILL. Not a real business.",
        "From: Kindling Software",
        "Invoice date: 2026-08-06",
        "Description: Plugin licence",
        "Total: 165.00",
        "GST: 20.00",
        f"ABN: {_spaced(kindling)}",
    ])
    _pdf(ROOT / "nobody-trading.pdf", [
        "MADE UP EXAMPLE BILL. Not a real business.",
        "From: Nobody Trading",
        "Invoice date: 2026-07-20",
        "Description: Oddment",
        "Total: 999.00",
        "GST: 90.82",
        f"ABN: {_spaced(nobody)}",
    ])
    _pdf(ROOT / "two-abns.pdf", [
        "MADE UP EXAMPLE BILL. Not a real business.",
        "From: Loom Advertising",
        "Invoice date: 2026-07-20",
        "Description: Poster boost",
        "Total: 396.00",
        "GST: 36.00",
        f"ABN: {_spaced(sable)}",
        f"ABN: {_spaced(bluegum)}",
    ])
    _pdf(ROOT / "no-abn.pdf", [
        "MADE UP EXAMPLE BILL. Not a real business.",
        "From: Cinder Repairs",
        "Invoice date: 2026-07-15",
        "Description: Door repair",
        "Total: 302.50",
        "GST: 27.50",
    ])
    _pdf(ROOT / "bad-checksum.pdf", [
        "MADE UP EXAMPLE BILL. Not a real business.",
        "From: Creek Road Grocer",
        "Invoice date: 2026-08-16",
        "Description: Plain milk and bread",
        "Total: 22.00",
        "GST: 2.00",
        "ABN: 12 345 678 901",
    ])
    _png(ROOT / "photo-of-bill.png")
    _auto_bills(sable)
    print(f"Wrote made-up bills in {ROOT}")


def _auto_bills(registered: str) -> None:
    """A bill for each GST purchase that does not already have a hand-written file."""
    payload = json.loads((ROOT.parent / "fennel-street-workshop.json").read_text(encoding="utf-8"))
    skip = {
        ("2026-07-01", "Sable Commercial", "Studio rent"),
        ("2026-08-17", "Bluegum Hosting", "Site hosting"),
        ("2026-08-06", "Kindling Software", "Plugin licence"),
        ("2026-07-20", "Loom Advertising", "Poster boost"),
        ("2026-07-15", "Cinder Repairs", "Door repair"),
        ("2026-08-16", "Creek Road Grocer", "Plain milk and bread"),
        ("2026-09-12", "Parcel Counter", "Large crate delivery"),
    }
    seen: set[tuple[str, str, str]] = set()
    index = 0
    for row in payload["transactions"]:
        if row.get("type") != "purchase" or Decimal(row["gst_amount"]) <= 0:
            continue
        key = (row["date"], row["contact"], row["description"])
        if key in skip or key in seen:
            continue
        seen.add(key)
        index += 1
        total = Decimal(row["net_amount"]) + Decimal(row["gst_amount"])
        _pdf(ROOT / f"auto-{index:02d}.pdf", [
            "MADE UP EXAMPLE BILL. Not a real business.",
            f"From: {row['contact']}",
            f"Invoice date: {row['date']}",
            f"Description: {row['description']}",
            f"Total: {total:.2f}",
            f"GST: {Decimal(row['gst_amount']):.2f}",
            f"ABN: {_spaced(registered)}",
        ])


def _spaced(number: str) -> str:
    return f"{number[0:2]} {number[2:5]} {number[5:8]} {number[8:11]}"


def _pdf(path: Path, lines: list[str]) -> None:
    path.write_bytes(_pdf_bytes(lines))


def _pdf_bytes(lines: list[str]) -> bytes:
    operations = ["BT", "/F1 11 Tf", "48 760 Td", "14 TL"]
    for index, line in enumerate(lines):
        if index:
            operations.append("T*")
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        operations.append(f"({safe}) Tj")
    operations.append("ET")
    stream = "\n".join(operations).encode("latin-1")
    content = b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
    font = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    page = (
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 5 0 R /Resources << /Font << /F1 4 0 R >> >> >>"
    )
    pages = b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>"
    catalog = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects = [catalog, pages, page, font, content]
    output = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(output)
    output += f"xref\n0 {len(objects) + 1}\n".encode()
    output += b"0000000000 65535 f \n"
    for offset in offsets:
        output += f"{offset:010d} 00000 n \n".encode()
    output += (
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(output)


def _png(path: Path) -> None:
    width, height = 40, 24
    colour = bytes((220, 214, 206))
    rows = b"".join(b"\x00" + colour * width for _ in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


if __name__ == "__main__":
    main()
