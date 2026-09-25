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
from pydantic import BaseModel, Field

from app.deps import TenantContext, get_tenant_context

router = APIRouter(prefix="/v1", tags=["members"])


class ProfileUpdate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    email: str = Field(min_length=3, max_length=320)
    timezone: str = Field(min_length=1, max_length=100)


@router.get("/members")
async def list_members(
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> list[dict]:
    """Return the caller-visible firm directory without crossing tenant boundaries."""
    rows = await ctx.db.fetch(
        "SELECT user_ref, full_name, role, clearance"
        " FROM firm_members WHERE tenant_id = $1::uuid ORDER BY full_name, user_ref",
        uuid.UUID(ctx.tenant_id),
    )
    return [
        {
            "user_ref": row["user_ref"],
            "full_name": row["full_name"],
            "role": row["role"],
            "clearance": row["clearance"],
        }
        for row in rows
    ]


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


@router.get("/profile")
async def get_profile(
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> dict:
    row = await ctx.db.fetchrow(
        "SELECT full_name, phone, email, timezone, role, clearance"
        " FROM firm_members WHERE tenant_id = $1::uuid AND user_ref = $2",
        uuid.UUID(ctx.tenant_id), ctx.user_ref,
    )
    if row is None:
        raise HTTPException(404, "No personnel record for this user yet.")
    return {**dict(row), "email": row["email"] or ""}


@router.put("/profile")
async def update_profile(
    body: ProfileUpdate,
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> dict:
    row = await ctx.db.fetchrow(
        "UPDATE firm_members SET full_name = $1, phone = $2, email = $3, timezone = $4"
        " WHERE tenant_id = $5::uuid AND user_ref = $6"
        " RETURNING full_name, phone, email, timezone, role, clearance",
        body.full_name.strip(), body.phone.strip() if body.phone else None,
        body.email.strip().lower(), body.timezone.strip(), uuid.UUID(ctx.tenant_id), ctx.user_ref,
    )
    if row is None:
        raise HTTPException(404, "No personnel record for this user yet.")
    return dict(row)
