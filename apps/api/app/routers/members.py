"""Personnel identity — current user's firm register record + tenant name (IA §2).

Exposes ``GET /v1/members/me``: the authenticated user's REAL personnel
identity (``full_name``, ``role``) from ``firm_members`` plus the firm's
``name`` from ``tenants``. This is the human's personnel name — deliberately
SEPARATE from the agent persona (agent_personas, S10-2). The AppShell header
and Home eyebrow render this, never a hardcoded "ANON" or a clearance string.

Thin read; RLS scopes firm_members/tenants to the caller's tenant. When the
caller isn't in the register yet (e.g. pre-registration), returns a 404 — the
frontend falls back to clearance/role gracefully.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.deps import TenantContext, get_tenant_context

router = APIRouter(prefix="/v1", tags=["members"])


@router.get("/members/me")
async def my_membership(
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> dict:
    """The caller's personnel record (name, role, clearance) + firm name."""
    row = await ctx.db.fetchrow(
        "SELECT fm.full_name, fm.role, fm.clearance AS member_clearance,"
        "       t.name AS firm_name"
        " FROM firm_members fm"
        " JOIN tenants t ON t.id = fm.tenant_id"
        " WHERE fm.tenant_id = $1::uuid AND fm.user_ref = $2",
        uuid.UUID(ctx.tenant_id),
        ctx.user_ref,
    )
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="No personnel record for this user yet.",
        )
    return {
        "full_name": row["full_name"],
        "role": row["role"],
        "clearance": row["member_clearance"] or ctx.clearance,
        "firm_name": row["firm_name"],
    }
