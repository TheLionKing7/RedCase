"""Practice operations — time capture (Addendum §9.1, task 3.9 sub-task 1).

  POST /v1/matters/{matter_id}/time   body {description, minutes?, started_at?,
                                             worked_at?, rate_ngn?, idempotency_key?}
                                          → 201 {id, minutes, total_minutes, ...}

Time capture is where work happens: the workbench timer and the `/time` channel
command both funnel into this endpoint. It is matter-scoped and entitlement-gated via
require_feature("ops.time") — a CORE entitlement (never in PREMIUM_FEATURES),
so the gate always ALLOWs for an active firm but still writes its
entitlement_events DECISION row (same "inert behind the existing entitlement
layer" meaning as core.dual_vault / comms.send).

Idempotency: a client retries at-least-once (timer stop can double-fire, Slack
retries). A unique index on (tenant_id, idempotency_key) collapses duplicate
submissions to one entry; a retry returns the existing entry, and reusing a key for
a different matter is a 409.

The matter FK bypasses RLS, so the matter is validated against the caller's tenant
before insert — no cross-tenant pinning (same rationale as channel attachment
checks). RLS tenant_isolation scopes every read.

ZDR: description is user content and is stored (it is the billable work product, not
an audit log) but never logged.
"""

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.deps import TenantContext, get_tenant_context
from app.entitlements import require_feature
from app.middleware.zdr import get_logger

log = get_logger("redcase.practice")

router = APIRouter(prefix="/v1", tags=["practice-ops"])


class TimeEntryCreate(BaseModel):
    description: str = Field(min_length=1, max_length=4000)
    minutes: int = Field(default=0)
    rate_ngn: Decimal | None = None
    worked_at: str | None = None
    idempotency_key: str | None = None


@router.post("/matters/{matter_id}/time", status_code=201)
async def create_time_entry(
    matter_id: uuid.UUID,
    body: TimeEntryCreate,
    _: None = Depends(require_feature("ops.time")),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> dict:
    # Matter FK bypasses RLS — verify the matter belongs to this tenant (no
    # cross-tenant pinning, no existence oracle).
    matter = await ctx.db.fetchval(
        "SELECT id FROM matters WHERE id = $1::uuid AND tenant_id = $2::uuid",
        matter_id,
        uuid.UUID(ctx.tenant_id),
    )
    if matter is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="matter not found")

    if body.minutes <= 0:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="minutes must be a positive integer (start/stop timers submit elapsed minutes)",
        )

    row = await ctx.db.fetchrow(
        "INSERT INTO time_entries"
        " (tenant_id, matter_id, user_ref, description, minutes, rate_ngn, idempotency_key)"
        " VALUES ($1, $2, $3, $4, $5, $6, $7)"
        " ON CONFLICT (tenant_id, idempotency_key) DO NOTHING"
        " RETURNING id, tenant_id, matter_id, user_ref, description, minutes,"
        "          rate_ngn, billed, worked_at",
        uuid.UUID(ctx.tenant_id),
        matter_id,
        ctx.user_ref,
        body.description,
        body.minutes,
        body.rate_ngn,
        body.idempotency_key,
    )
    if row is None:
        # Idempotent retry: the entry already exists — return it.
        row = await ctx.db.fetchrow(
            "SELECT id, tenant_id, matter_id, user_ref, description, minutes,"
            " rate_ngn, billed, worked_at FROM time_entries"
            " WHERE tenant_id = $1::uuid AND idempotency_key = $2"
            "   AND matter_id = $3::uuid",
            uuid.UUID(ctx.tenant_id),
            body.idempotency_key,
            matter_id,
        )
        if row is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="idempotency_key already used for a different matter",
            )
    total = await ctx.db.fetchval(
        "SELECT COALESCE(SUM(minutes), 0) FROM time_entries WHERE matter_id = $1::uuid",
        matter_id,
    )
    log.info(
        "time_entry_recorded",
        matter_id=str(matter_id),
        minutes=row["minutes"],
        billed=row["billed"],
        tenant_id=ctx.tenant_id,
    )
    return {
        "id": str(row["id"]),
        "matter_id": str(row["matter_id"]),
        "description": row["description"],
        "minutes": row["minutes"],
        "rate_ngn": (
            float(row["rate_ngn"]) if row["rate_ngn"] is not None else None
        ),
        "billed": row["billed"],
        "worked_at": row["worked_at"].isoformat(),
        "total_minutes": total,
    }


@router.get("/matters/{matter_id}/time")
async def list_time_entries(
    matter_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> dict:
    # RLS tenant_isolation scopes to the caller's tenant; no existence oracle —
    # a foreign matter simply returns zero rows.
    rows = await ctx.db.fetch(
        "SELECT id, user_ref, description, minutes, rate_ngn, billed, worked_at"
        " FROM time_entries WHERE matter_id = $1::uuid ORDER BY worked_at",
        matter_id,
    )
    return {
        "matter_id": str(matter_id),
        "total_minutes": sum(r["minutes"] for r in rows),
        "entries": [
            {
                "id": str(r["id"]),
                "user_ref": r["user_ref"],
                "description": r["description"],
                "minutes": r["minutes"],
                "rate_ngn": (
                    float(r["rate_ngn"]) if r["rate_ngn"] is not None else None
                ),
                "billed": r["billed"],
                "worked_at": r["worked_at"].isoformat(),
            }
            for r in rows
        ],
    }
