"""Matter assignment + Firm Command progress panel — Addendum-S10 §10.4 (S10-3).

  * ``POST /v1/matters/{matter_id}/assign`` — set assigned_to + optional progress_note.
  * ``GET  /v1/matters/{matter_id}``      — a matter + its assignment.
  * ``GET  /v1/matters/my``               — matters where assigned_to = me.
  * ``GET  /v1/firm/matters/progress``   — firm-admin-gated panel composing
    EXISTING data: analyses count + unbilled time per matter.

RLS: matters.tenant_isolation (WITH CHECK, migration 0023) scopes reads AND
writes. The matter FK bypasses RLS, so assign validates the matter against the
caller's tenant first (no cross-tenant pinning — same rationale as practice.py).
The progress panel is a Firm Command surface -> require_firm_admin (§8.5).

ZDR: assigned_to is a ref id; progress_note is firm operational content (like
matter_ref), never logged.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.deps import TenantContext, get_tenant_context, require_firm_admin
from app.middleware.zdr import get_logger

log = get_logger("redcase.matters")

router = APIRouter(prefix="/v1", tags=["matters"])

_WHO_CAN_ASSIGN = {"PARTNER", "ADMIN"}


class AssignRequest(BaseModel):
    assigned_to: str = Field(min_length=1, max_length=256)
    progress_note: str | None = Field(default=None, max_length=4000)


async def _assignee_in_tenant(ctx: TenantContext, assignee_ref: str) -> bool:
    """True when assignee_ref is a real user of THIS tenant.

    A user is "in the firm" if they accepted an invite (firm_invites
    accepted_user_ref, status ACCEPTED). Tenant-scoped under RLS — no oracle.
    """
    row = await ctx.db.fetchval(
        "SELECT 1 FROM firm_invites"
        " WHERE tenant_id = $1::uuid AND accepted_user_ref = $2"
        "   AND status = 'ACCEPTED'"
        " LIMIT 1",
        uuid.UUID(ctx.tenant_id),
        assignee_ref,
    )
    return row is not None


async def _get_matter(ctx: TenantContext, matter_id: uuid.UUID) -> dict | None:
    """Fetch a matter within the caller's tenant, or None (no existence oracle)."""
    return await ctx.db.fetchrow(
        "SELECT id, matter_ref, status, assigned_to, progress_note"
        " FROM matters WHERE id = $1::uuid AND tenant_id = $2::uuid",
        matter_id,
        uuid.UUID(ctx.tenant_id),
    )

@router.get("/matters/my")
async def my_matters(
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> dict:
    """Matters where the caller is the assigned lead (Workbench "my matters")."""
    rows = await ctx.db.fetch(
        "SELECT id, matter_ref, status, assigned_to, progress_note"
        " FROM matters WHERE assigned_to = $1 ORDER BY opened_at DESC",
        ctx.user_ref,
    )
    return {
        "matters": [
            {
                "id": str(r["id"]),
                "matter_ref": r["matter_ref"],
                "status": r["status"],
                "assigned_to": r["assigned_to"],
                "progress_note": r["progress_note"],
            }
            for r in rows
        ]
    }


@router.get("/matters/{matter_id}")
async def get_matter(
    matter_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> dict:
    """A matter + its assignment (single card / rollback view)."""
    row = await _get_matter(ctx, matter_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="matter not found")
    return {
        "id": str(row["id"]),
        "matter_ref": row["matter_ref"],
        "status": row["status"],
        "assigned_to": row["assigned_to"],
        "progress_note": row["progress_note"],
    }


@router.post("/matters/{matter_id}/assign")
async def assign_lead(
    matter_id: uuid.UUID,
    body: AssignRequest,
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> dict:
    """Assign a lead counsel (+ optional progress note).

    Only PARTNER/ADMIN clearance or firm-admin may assign — mirrors the invite
    authority ("who can steer firm work") plus firm-admin.
    """
    if ctx.clearance not in _WHO_CAN_ASSIGN and not ctx.is_firm_admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="assigning a matter requires PARTNER/ADMIN clearance or firm-admin",
        )
    row = await _get_matter(ctx, matter_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="matter not found")
    if not await _assignee_in_tenant(ctx, body.assigned_to):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="assignee is not a licensed user of this firm",
        )
    updated = await ctx.db.fetchrow(
        "UPDATE matters SET assigned_to = $1, progress_note = $2"
        " WHERE id = $3::uuid AND tenant_id = $4::uuid"
        " RETURNING id, matter_ref, status, assigned_to, progress_note",
        body.assigned_to,
        body.progress_note,
        matter_id,
        uuid.UUID(ctx.tenant_id),
    )
    if updated is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="matter not found")
    log.info(
        "matter_assigned",
        matter_id=str(matter_id),
        assigned_to=body.assigned_to,
        tenant_id=ctx.tenant_id,
    )
    return {
        "id": str(updated["id"]),
        "matter_ref": updated["matter_ref"],
        "status": updated["status"],
        "assigned_to": updated["assigned_to"],
        "progress_note": updated["progress_note"],
    }


@router.get("/firm/matters/progress")
async def matter_progress(
    ctx: TenantContext = Depends(require_firm_admin),  # noqa: B008
) -> dict:
    """Firm Command matter-progress panel.

    Composes EXISTING data per matter (no new model beyond 0023's two columns):
    lead counsel, status, analyses run, unbilled minutes.
    """
    rows = await ctx.db.fetch(
        "SELECT m.id, m.matter_ref, m.status, m.assigned_to, m.progress_note,"
        "       (SELECT COUNT(*) FROM document_analyses da"
        "         WHERE da.matter_id = m.id) AS analyses_count,"
        "       (SELECT COALESCE(SUM(t.minutes), 0) FROM time_entries t"
        "         WHERE t.matter_id = m.id) AS time_minutes"
        "  FROM matters m"
        "  ORDER BY m.opened_at DESC"
    )
    return {
        "matters": [
            {
                "id": str(r["id"]),
                "matter_ref": r["matter_ref"],
                "status": r["status"],
                "assigned_to": r["assigned_to"],
                "progress_note": r["progress_note"],
                "analyses_count": r["analyses_count"],
                "time_minutes": r["time_minutes"],
            }
            for r in rows
        ]
    }

