"""Invoice PDF export — obsidian/crimson brand letterhead (Addendum §9.1 feature (b)).

ZDR (§9.1): the PDF is the billable work product (like time_entries.description),
not an audit log — it carries the per-line descriptions by design and is returned to the
requesting firm only. No document text ever enters it.

Built on pymupdf (already a project dependency, used by the ingestion pipeline) — no new
runtime deps. Brand tokens come from app.config (BRAND_CRIMSON #D0021B,
BRAND_OBSIDIAN #0F1115; gold accent #E2C044 for the header rule).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import pymupdf

from app.config import BRAND_CRIMSON, BRAND_OBSIDIAN, BRAND_VELLUM

# Money formatting — naira (the firm's domicile currency, §9.1 amount_ngn).
FORMAT_NGN = "₦{:,.2f}"


def _fmt(d: date | None) -> str:
    return d.strftime("%d %b %Y") if d else "—"


def _two(value: float | int | Decimal) -> str:
    return FORMAT_NGN.format(float(value))


class _Colors:
    """Named colors used by the letterhead; pymupdf wants (r,g,b) tuples."""

    crimson: tuple[float, float, float]
    obsidian: tuple[float, float, float]
    gold: tuple[float, float, float]
    muted: tuple[float, float, float]

    def __init__(self) -> None:
        def rgb(hex_: str) -> tuple[int, int, int]:
            h = hex_.lstrip("#")
            return (
                int(h[0:2], 16) / 255,
                int(h[2:4], 16) / 255,
                int(h[4:6], 16) / 255,
            )

        self.crimson = rgb(BRAND_CRIMSON)
        self.obsidian = rgb(BRAND_OBSIDIAN)
        self.gold = rgb(BRAND_VELLUM)
        # Steel tint of the obsidian family (design-system P3) for secondary text.
        self.muted = (142 / 255, 153 / 255, 168 / 255)


@dataclass
class InvoiceLine:
    """A single billable row on the invoice (snapshot of a billed time entry)."""

    description: str
    minutes: int
    rate_ngn: Decimal | None
    amount_ngn: Decimal


def build_invoice_pdf(
    *,
    firm_name: str,
    number: str,
    matter_ref: str,
    status: str,
    created_at: datetime,
    due_date: date | None,
    lines: list[InvoiceLine],
    subtotal: Decimal,
    paid_total: Decimal,
) -> bytes:
    """Render the invoice document and return the PDF bytes."""
    colors = _Colors()
    doc = pymupdf.open()
    page = doc.new_page(width=595.0, height=842.0)  # A4 portrait
    tw = page.rect.width
    margin = 56.0
    y = 56.0

    # --- Letterhead ---
    page.draw_rect(pymupdf.Rect(0, 0, tw, 8), color=None, fill=colors.crimson)
    page.draw_rect(pymupdf.Rect(0, 8, tw, 12), color=None, fill=colors.obsidian)
    page.insert_text(
        (margin, y),
        firm_name,
        fontsize=22,
        fontname="helv",
        color=colors.obsidian,
    )
    page.insert_text(
        (margin, y + 16),
        "INVOICE",
        fontsize=13,
        fontname="helv",
        color=colors.crimson,
    )
    page.draw_line(
        pymupdf.Point(margin, y + 26),
        pymupdf.Point(tw - margin, y + 26),
        color=colors.gold,
        width=1.2,
    )
    y += 56

    # --- Meta block ---
    meta = [
        ("Invoice No.", number),
        ("Status", status),
        ("Matter", matter_ref),
        ("Date", _fmt(created_at.date())),
        ("Due", _fmt(due_date)),
    ]
    for label, value in meta:
        page.insert_text(
            (margin, y), f"{label}:", fontsize=10, fontname="helv", color=colors.muted
        )
        page.insert_text(
            (margin + 80, y), value, fontsize=10, fontname="helv", color=colors.obsidian
        )
        y += 16
    y += 16

    # --- Lines table ---
    col_desc = margin
    col_min = 320.0
    col_rate = 390.0
    col_amt = 460.0
    page.insert_text(
        (col_desc, y), "Description", fontsize=9, fontname="helv", color=colors.muted
    )
    page.insert_text((col_min, y), "Mins", fontsize=9, fontname="helv", color=colors.muted)
    page.insert_text((col_rate, y), "Rate", fontsize=9, fontname="helv", color=colors.muted)
    page.insert_text((col_amt, y), "Amount", fontsize=9, fontname="helv", color=colors.muted)
    page.draw_line(
        pymupdf.Point(margin, y + 4),
        pymupdf.Point(tw - margin, y + 4),
        color=colors.obsidian,
        width=0.6,
    )
    y += 20

    for line in lines:
        page.insert_text(
            (col_desc, y), line.description, fontsize=9, fontname="helv", color=colors.obsidian
        )
        page.insert_text(
            (col_min, y), str(line.minutes), fontsize=9, fontname="helv", color=colors.obsidian
        )
        page.insert_text(
            (col_rate, y),
            _two(line.rate_ngn) if line.rate_ngn is not None else "—",
            fontsize=9,
            fontname="helv",
            color=colors.obsidian,
        )
        page.insert_text(
            (col_amt, y), _two(line.amount_ngn), fontsize=9, fontname="helv", color=colors.obsidian
        )
        y += 16

    y += 8
    page.insert_text(
        (col_rate, y), "Subtotal", fontsize=10, fontname="helv", color=colors.muted
    )
    page.insert_text(
        (col_amt, y), _two(subtotal), fontsize=10, fontname="helv", color=colors.crimson
    )
    y += 16
    if paid_total and paid_total > 0:
        page.insert_text(
            (col_rate, y), "Paid", fontsize=10, fontname="helv", color=colors.muted
        )
        page.insert_text(
            (col_amt, y), _two(paid_total), fontsize=10, fontname="helv", color=colors.muted
        )
        y += 16
        page.insert_text(
            (col_rate, y), "Balance", fontsize=10, fontname="helv", color=colors.obsidian
        )
        page.insert_text(
            (col_amt, y),
            _two(subtotal - paid_total),
            fontsize=10,
            fontname="helv",
            color=colors.obsidian,
        )

    doc.set_metadata(
        {
            "title": f"Invoice {number}",
            "author": firm_name,
            "producer": "RedCase",
        }
    )
    data = doc.tobytes()
    doc.close()
    return data

