"""Practice operations — invoicing + payments (Addendum §9.1, task 3.9 sub-task 2).

  POST /v1/matters/{matter_id}/invoice            → 201 {invoice}   unbilled entries → DRAFT
  GET  /v1/matters/{matter_id}/invoices        → list
  GET  /v1/invoices/{invoice_id}                → detail
  POST /v1/invoices/{invoice_id}/send           → SENT (records sent_at)
  GET  /v1/invoices/{invoice_id}.pdf            → application/pdf, brand letterhead
  POST /v1/invoices/{invoice_id}/payments       → records payment; recomputes status
  GET  /v1/receivables/aging                  → per-bucket aging

Gated by require_feature("ops.invoicing") — a CORE entitlement (never in
PREMIUM_FEATURES), so the gate always ALLOWs for an active firm but still writes its
entitlement_events DECISION row (same "inert behind the existing entitlement layer"
meaning as ops.time / comms.send).

Payment semantics (doc §9.1): recording a payment transitions status from
DRAFT/SENT → PARTIAL when under the total and → PAID at the total. WRITTEN_OFF is set
directly by the firm. Status transitions are guarded in the router (a PAID/WRITTEN_OFF
invoice cannot be amended, re-sent, or paid).

rate_ngn is an hourly rate (NGN/hour); a line's amount = minutes/60 * rate. The doc's
"rate_ngn NULL = use matter default" pointer resolves to "not billable" (no matter-default
column exists), so a firm must set a rate to bill.

ZDR: line descriptions are the billable work product (same class as timesheet work), stored and
returned to the firm only — never logged.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.deps import TenantContext, get_tenant_context
from app.entitlements import require_feature
from app.invoicing_pdf import InvoiceLine, build_invoice_pdf
from app.middleware.zdr import get_logger

log = get_logger("redcase.invoicing")

router = APIRouter(prefix="/v1", tags=["practice-invoicing"])

INVOICE_NUMBER_PREFIX = "RC-"


class LineOut(BaseModel):
    time_entry_id: str
    description: str
    minutes: int
    rate_ngn: Decimal | None = None
    amount_ngn: Decimal


class InvoiceOut(BaseModel):
    id: str
    matter_id: str
    number: str
    status: str
    amount_ngn: Decimal
    paid_ngn: Decimal
    balance_ngn: Decimal
    due_date: str | None = None
    sent_at: str | None = None
    created_at: str
    lines: list[LineOut] = Field(default_factory=list)


class AgingBucket(BaseModel):
    label: str
    total_ngn: Decimal


class InvoiceCreate(BaseModel):
    due_date: date | None = None


class PaymentCreate(BaseModel):
    amount_ngn: Decimal = Field(gt=0)
    method: str = "BANK_TRANSFER"
    reference: str | None = None


def _as_invoice(row: dict) -> InvoiceOut:
    return InvoiceOut(
        id=str(row["id"]),
        matter_id=str(row["matter_id"]),
        number=row["number"],
        status=row["status"],
        amount_ngn=row["amount_ngn"],
        paid_ngn=row["paid_ngn"],
        balance_ngn=row["balance_ngn"],
        due_date=row["due_date"].isoformat() if row["due_date"] else None,
        sent_at=row["sent_at"].isoformat() if row["sent_at"] else None,
        created_at=row["created_at"].isoformat(),
        lines=row.get("lines", []),
    )


def _require_status(*allowed: str):
    def _check(current: str) -> None:
        if current not in allowed:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"invoice status {current} does not allow this action "
                f"(allowed: {', '.join(allowed)})",
            )

    return _check


async def _next_invoice_number(ctx: TenantContext, tenant_id: str) -> str:
    """Firm-numbered, per-tenant sequence: RC-<N> (UNIQUE(tenant_id, number))."""
    max_num = await ctx.db.fetchval(
        "SELECT MAX(CAST(SUBSTRING(number FROM '^RC-([0-9]+)') AS BIGINT))"
        " FROM invoices WHERE tenant_id = $1::uuid",
        uuid.UUID(tenant_id),
    )
    nxt = 1 if max_num is None else int(max_num) + 1
    return f"{INVOICE_NUMBER_PREFIX}{nxt:05d}"

@router.post(
    "/matters/{matter_id}/invoice",
    response_model=InvoiceOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_invoice(
    matter_id: uuid.UUID,
    body: InvoiceCreate,
    _: None = Depends(require_feature("ops.invoicing")),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> InvoiceOut:
    """Build a DRAFT invoice from the matter's UNBILLED time entries.

    Continuity with sub-task 1: entries recorded via /v1/matters/{id}/time (or the
    /time channel command) become invoiceable here. All unbilled, rated entries are billed
    atomically and marked billed=TRUE so no entry is double-billed.
    """
    # Matter FK bypasses RLS — validate tenancy explicitly (no cross-tenant pinning).
    matter = await ctx.db.fetchrow(
        "SELECT id, matter_ref FROM matters WHERE id = $1::uuid",
        matter_id,
    )
    if matter is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="matter not found")

    unbilled = await ctx.db.fetch(
        "SELECT id, description, minutes, rate_ngn FROM time_entries"
        " WHERE matter_id = $1::uuid AND billed = FALSE ORDER BY worked_at",
        matter_id,
    )
    if not unbilled:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="no unbilled time entries on this matter",
        )
    rated = [r for r in unbilled if r["rate_ngn"] is not None]
    amount = sum(
        (Decimal(r["minutes"]) / 60 * Decimal(r["rate_ngn"]) for r in rated),
        Decimal("0"),
    )
    if amount <= 0:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="sum of unbilled entries must be positive "
            "(set an hourly rate_ngn on time entries)",
        )


    number = await _next_invoice_number(ctx, ctx.tenant_id)
    invoice_id = uuid.uuid4()
    await ctx.db.execute(
        "INSERT INTO invoices"
        " (id, tenant_id, matter_id, number, status, amount_ngn, due_date)"
        " VALUES ($1, $2, $3, $4, 'DRAFT', $5, $6)",
        invoice_id,
        uuid.UUID(ctx.tenant_id),
        matter_id,
        number,
        amount,
        body.due_date,
    )
    for row in rated:
        line_amount = Decimal(row["minutes"]) / 60 * Decimal(row["rate_ngn"])
        await ctx.db.execute(
            "INSERT INTO invoice_line_items"
            " (tenant_id, invoice_id, time_entry_id, description, minutes,"
            "  rate_ngn, amount_ngn)"
            " VALUES ($1, $2, $3, $4, $5, $6, $7)",
            uuid.UUID(ctx.tenant_id),
            invoice_id,
            row["id"],
            row["description"],
            row["minutes"],
            row["rate_ngn"],
            line_amount,
        )
        await ctx.db.execute(
            "UPDATE time_entries SET billed = TRUE"
            " WHERE id = $1 AND tenant_id = $2",
            row["id"],
            uuid.UUID(ctx.tenant_id),
        )
    log.info(
        "invoice_created",
        invoice_id=str(invoice_id),
        matter_id=str(matter_id),
        amount_ngn=str(amount),
        tenant_id=ctx.tenant_id,
    )
    return _as_invoice(
        {
            "id": str(invoice_id),
            "matter_id": str(matter_id),
            "number": number,
            "status": "DRAFT",
            "amount_ngn": amount,
            "paid_ngn": Decimal("0"),
            "balance_ngn": amount,
            "due_date": body.due_date,
            "sent_at": None,
            "created_at": datetime.now(UTC),
        }
    )


async def _load_invoice(
    ctx: TenantContext, invoice_id: str, with_lines: bool = False
) -> dict:
    row = await ctx.db.fetchrow(
        "SELECT i.id, i.matter_id, i.number, i.status, i.amount_ngn, i.due_date,"
        " i.sent_at, i.created_at,"
        " (SELECT COALESCE(SUM(p.amount_ngn), 0) FROM payments p"
        "   WHERE p.invoice_id = i.id) AS paid_ngn"
        " FROM invoices i WHERE i.id = $1::uuid",
        uuid.UUID(invoice_id),
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="invoice not found")
    out = dict(row)
    out["balance_ngn"] = out["amount_ngn"] - out["paid_ngn"]
    if with_lines:
        lines = await ctx.db.fetch(
            "SELECT time_entry_id, description, minutes, rate_ngn, amount_ngn"
            " FROM invoice_line_items WHERE invoice_id = $1::uuid ORDER BY id",
            uuid.UUID(invoice_id),
        )
        out["lines"] = [
            LineOut(
                time_entry_id=str(r["time_entry_id"]),
                description=r["description"],
                minutes=r["minutes"],
                rate_ngn=r["rate_ngn"],
                amount_ngn=r["amount_ngn"],
            )
            for r in lines
        ]
    else:
        out["lines"] = []
    return out


@router.get("/matters/{matter_id}/invoices", response_model=list[InvoiceOut])
async def list_matter_invoices(
    matter_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> list[InvoiceOut]:
    rows = await ctx.db.fetch(
        "SELECT i.id, i.matter_id, i.number, i.status, i.amount_ngn, i.due_date,"
        " i.sent_at, i.created_at,"
        " (SELECT COALESCE(SUM(p.amount_ngn), 0) FROM payments p"
        "   WHERE p.invoice_id = i.id) AS paid_ngn"
        " FROM invoices i WHERE i.matter_id = $1::uuid ORDER BY i.created_at DESC",
        matter_id,
    )
    out = []
    for r in rows:
        d = dict(r)
        d["balance_ngn"] = d["amount_ngn"] - d["paid_ngn"]
        d["lines"] = []
        out.append(_as_invoice(d))
    return out


@router.get("/invoices/{invoice_id}.pdf")
async def get_invoice_pdf(
    invoice_id: str,
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> Response:
    """Export the invoice with the obsidian/crimson brand letterhead (Addendum 9.1 (b))."""
    inv = await _load_invoice(ctx, invoice_id, with_lines=True)
    firm = await ctx.db.fetchval(
        "SELECT name FROM tenants WHERE id = $1::uuid", uuid.UUID(ctx.tenant_id)
    )
    matter = await ctx.db.fetchval(
        "SELECT matter_ref FROM matters WHERE id = $1::uuid",
        uuid.UUID(str(inv["matter_id"])),
    )
    lines = [
        InvoiceLine(
            description=li.description,
            minutes=li.minutes,
            rate_ngn=li.rate_ngn,
            amount_ngn=li.amount_ngn,
        )
        for li in inv["lines"]
    ]
    data = build_invoice_pdf(
        firm_name=firm or "RedCase",
        number=inv["number"],
        matter_ref=matter or inv["matter_id"],
        status=inv["status"],
        created_at=inv["created_at"],
        due_date=inv["due_date"],
        lines=lines,
        subtotal=inv["amount_ngn"],
        paid_total=inv["paid_ngn"],
    )
    filename = f"{inv['number']}.pdf"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/invoices/{invoice_id}", response_model=InvoiceOut)
async def get_invoice(
    invoice_id: str,
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> InvoiceOut:
    return _as_invoice(await _load_invoice(ctx, invoice_id, with_lines=True))


@router.post("/invoices/{invoice_id}/send", response_model=InvoiceOut)
async def send_invoice(
    invoice_id: str,
    _: None = Depends(require_feature("ops.invoicing")),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> InvoiceOut:
    """Mark a DRAFT invoice as SENT (starts the aging clock, records sent_at)."""
    row = await ctx.db.fetchrow(
        "SELECT id FROM invoices WHERE id = $1::uuid",
        uuid.UUID(invoice_id),
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="invoice not found")
    current = await ctx.db.fetchval(
        "SELECT status FROM invoices WHERE id = $1::uuid",
        uuid.UUID(invoice_id),
    )
    _require_status("DRAFT")(current)
    await ctx.db.execute(
        "UPDATE invoices SET status = 'SENT', sent_at = now()"
        " WHERE id = $1::uuid",
        uuid.UUID(invoice_id),
    )
    log.info("invoice_sent", invoice_id=invoice_id, tenant_id=ctx.tenant_id)
    return await get_invoice(invoice_id, ctx)


@router.post(
    "/invoices/{invoice_id}/payments",
    response_model=InvoiceOut,
    status_code=status.HTTP_201_CREATED,
)
async def record_payment(
    invoice_id: str,
    body: PaymentCreate,
    _: None = Depends(require_feature("ops.invoicing")),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> InvoiceOut:
    """Record a payment and recompute the status (DRAFT/SENT → PARTIAL/PAID)."""
    row = await ctx.db.fetchrow(
        "SELECT status, amount_ngn,"
        " (SELECT COALESCE(SUM(p.amount_ngn), 0) FROM payments p"
        "   WHERE p.invoice_id = invoices.id) AS paid_ngn"
        " FROM invoices WHERE id = $1::uuid",
        uuid.UUID(invoice_id),
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="invoice not found")
    _require_status("DRAFT", "SENT", "PARTIAL")(row["status"])

    await ctx.db.execute(
        "INSERT INTO payments"
        " (id, tenant_id, invoice_id, amount_ngn, method, reference)"
        " VALUES ($1, $2, $3, $4, $5, $6)",
        uuid.uuid4(),
        uuid.UUID(ctx.tenant_id),
        uuid.UUID(invoice_id),
        body.amount_ngn,
        body.method,
        body.reference,
    )
    new_paid = row["paid_ngn"] + body.amount_ngn
    new_status = "PAID" if new_paid >= row["amount_ngn"] else "PARTIAL"
    await ctx.db.execute(
        "UPDATE invoices SET status = $2 WHERE id = $1::uuid",
        uuid.UUID(invoice_id),
        new_status,
    )
    log.info(
        "payment_recorded",
        invoice_id=invoice_id,
        amount_ngn=str(body.amount_ngn),
        tenant_id=ctx.tenant_id,
    )
    return await get_invoice(invoice_id, ctx)


@router.get("/receivables/aging", response_model=list[AgingBucket])
async def receivables_aging(
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> list[AgingBucket]:
    """Per-firm receivables aging: outstanding SENT/PARTIAL balances bucketed by age.

    Age is measured from sent_at (or created_at pre-send); DRAFT and WRITTEN_OFF invoices
    carry no balance due and are excluded.
    """
    rows = await ctx.db.fetch(
        """
        WITH unbilled AS (
            SELECT i.id, i.amount_ngn,
                   COALESCE(SUM(p.amount_ngn), 0) AS paid_ngn,
                   COALESCE(i.sent_at, i.created_at) AS age_from
            FROM invoices i
            LEFT JOIN payments p ON p.invoice_id = i.id
            WHERE i.status IN ('SENT','PARTIAL')
            GROUP BY i.id
        ),
        ages AS (
            SELECT amount_ngn, paid_ngn,
                   (now() AT TIME ZONE 'UTC')::date - age_from::date AS days
            FROM unbilled
        )
        SELECT
            CASE
                WHEN days < 0 THEN 'CURRENT'
                WHEN days <= 30 THEN '0-30'
                WHEN days <= 60 THEN '31-60'
                WHEN days <= 90 THEN '61-90'
                ELSE '90+'
            END AS bucket,
            SUM(amount_ngn - paid_ngn) AS total_ngn
        FROM ages
        GROUP BY bucket
        """
    )
    order = ["CURRENT", "0-30", "31-60", "61-90", "90+"]
    by_label = {r["bucket"]: Decimal(r["total_ngn"]) for r in rows}
    return [
        AgingBucket(label=label, total_ngn=by_label.get(label, Decimal("0")))
        for label in order
    ]
