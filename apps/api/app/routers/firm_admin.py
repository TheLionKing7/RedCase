"""Firm Command — admin-capability surfaces (Addendum §8.5, audit H3).

§8.5 rules admin capability as an ORTHOGONAL dimension to clearance: a separate,
grantable flag (JWT ``app_metadata.is_firm_admin``), NOT derived from clearance.
Every endpoint here is gated by ``require_firm_admin`` (server-side, never UI
hiding) and serves a Firm Command widget composed from existing data:

  * seats          — subscriptions billing anchors (plan, max/current seats, status).
  * invites        — the firm's invite ledger (who was invited, role, state).
  * transparency   — a redacted audit feed (query_audit + entitlement_events +
                      firm_admins), ZDR-clean (metadata only).
  * admin ledger   — the append-only firm_admins grant/revoke trail + POST to grant
                      or revoke admin capability (each event is a row; immutability
                      is a DB grant in conftest, same as the other audit tables).

Admin grant/revoke is itself an admin act: it writes a firm_admins row and is
logged. The live ``is_firm_admin`` flag lives in Supabase ``app_metadata`` (set at
provisioning; the grant/revoke evolution is trailed here).

ZDR: firm_admins/invite rows carry ids + steps, never emails or document content.
Transparency reuses the audit router's already-redacted projection.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.deps import require_firm_admin
from app.deps import TenantContext
from app.middleware.zdr import get_logger

log = get_logger("redcase.firm_admin")

router = APIRouter(prefix="/v1/firm", tags=["firm-admin"])


class AdminGrantIn(BaseModel):
    user_ref: str = Field(min_length=1, max_length=256)
    action: str = Field(pattern="^(GRANTED|REVOKED)$")


@router.get("/admin/overview")
async def admin_overview(
    ctx: TenantContext = Depends(require_firm_admin),  # noqa: B008
) -> dict:
    """Seats overview — billing anchors for the Firm Command seats widget."""
    row = await ctx.db.fetchrow(
        "SELECT plan, status, max_seats, current_seats FROM subscriptions"
        " WHERE tenant_id = $1::uuid",
        uuid.UUID(ctx.tenant_id),
    )
    return {
        "seats": {
            "plan": row["plan"] if row else "CORE",
            "status": row["status"] if row else "ACTIVE",
            "max_seats": row["max_seats"] if row else 0,
            "current_seats": row["current_seats"] if row else 0,
        }
    }


@router.get("/admin/invites")
async def admin_invites(
    ctx: TenantContext = Depends(require_firm_admin),  # noqa: B008
) -> dict:
    """The firm's invite ledger — who was invited, role, state (no emails)."""
    rows = await ctx.db.fetch(
        "SELECT id, role, clearance, status, invited_by, created_at"
        " FROM firm_invites WHERE tenant_id = $1::uuid"
        " ORDER BY created_at DESC LIMIT 100",
        uuid.UUID(ctx.tenant_id),
    )
    return {
        "invites": [
            {
                "id": str(r["id"]),
                "role": r["role"],
                "clearance": r["clearance"],
                "status": r["status"],
                "invited_by": r["invited_by"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]
    }


@router.get("/admin/transparency")
async def admin_transparency(
    ctx: TenantContext = Depends(require_firm_admin),  # noqa: B008
) -> dict:
    """Firm Command transparency feed — redacted audit metadata (ZDR-clean).

    Same projection as the audit router (query_audit + entitlement_events + the
    firm_admins ledger). Never answer_text/citations/question bodies — metadata only.
    """
    qa = await ctx.db.fetch(
        "SELECT question_hash, threshold_passed, latency_ms, serving_provider,"
        " serving_model, created_at FROM query_audit"
        " WHERE tenant_id = $1::uuid ORDER BY created_at DESC LIMIT 200",
        uuid.UUID(ctx.tenant_id),
    )
    ee = await ctx.db.fetch(
        "SELECT feature, decision, created_at FROM entitlement_events"
        " WHERE tenant_id = $1::uuid ORDER BY created_at DESC LIMIT 200",
        uuid.UUID(ctx.tenant_id),
    )
    ad = await ctx.db.fetch(
        "SELECT user_ref, action, granted_by, created_at FROM firm_admins"
        " WHERE tenant_id = $1::uuid ORDER BY created_at DESC LIMIT 200",
        uuid.UUID(ctx.tenant_id),
    )
    return {
        "query": [
            {
                "question_hash": r["question_hash"],
                "threshold_passed": r["threshold_passed"],
                "latency_ms": r["latency_ms"],
                "serving_provider": r["serving_provider"],
                "serving_model": r["serving_model"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in qa
        ],
        "entitlements": [
            {
                "feature": r["feature"],
                "decision": r["decision"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in ee
        ],
        "admins": [
            {
                "user_ref": r["user_ref"],
                "action": r["action"],
                "granted_by": r["granted_by"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in ad
        ],
    }


@router.get("/admin/admins")
async def admin_ledger(
    ctx: TenantContext = Depends(require_firm_admin),  # noqa: B008
) -> dict:
    """The append-only admin grant/revoke trail."""
    rows = await ctx.db.fetch(
        "SELECT id, user_ref, action, granted_by, created_at FROM firm_admins"
        " WHERE tenant_id = $1::uuid ORDER BY created_at DESC LIMIT 100",
        uuid.UUID(ctx.tenant_id),
    )
    return {
        "entries": [
            {
                "id": str(r["id"]),
                "user_ref": r["user_ref"],
                "action": r["action"],
                "granted_by": r["granted_by"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]
    }


@router.post("/admin/grants", status_code=201)
async def record_admin_grant(
    body: AdminGrantIn,
    ctx: TenantContext = Depends(require_firm_admin),  # noqa: B008
) -> dict:
    """Record a GRANTED/REVOKED admin event on the append-only firm_admins ledger.

    Every admin grant/revoke is an admin act and lands as an immutable row. The live
    ``is_firm_admin`` flag is carried on the user's JWT ``app_metadata`` claim (set
    via the Supabase Admin API at provisioning); this endpoint is the audit trail of that
    capability, never a silent toggle.
    """
    event_id = uuid.uuid4()
    await ctx.db.execute(
        "INSERT INTO firm_admins (id, tenant_id, user_ref, action, granted_by)"
        " VALUES ($1, $2, $3, $4, $5)",
        event_id,
        uuid.UUID(ctx.tenant_id),
        body.user_ref,
        body.action,
        ctx.user_ref,
    )
    log.info(
        "firm_admin_event",
        event_id=str(event_id),
        user_ref=body.user_ref,
        action=body.action,
        granted_by=ctx.user_ref,
        tenant_id=ctx.tenant_id,
    )
    return {
        "id": str(event_id),
        "user_ref": body.user_ref,
        "action": body.action,
        "granted_by": ctx.user_ref,
        "created_at": datetime.now(UTC).isoformat(),
    }


@router.get("/admin/settings")
async def firm_settings(
    ctx: TenantContext = Depends(require_firm_admin),  # noqa: B008
) -> dict:
    """Firm settings widget — tenant identity surfaced for the admin (no PII)."""
    row = await ctx.db.fetchrow(
        "SELECT name, slug, jurisdiction FROM tenants WHERE id = $1::uuid",
        uuid.UUID(ctx.tenant_id),
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="firm not found")
    return {
        "firm": {
            "name": row["name"],
            "slug": row["slug"],
            "jurisdiction": row["jurisdiction"],
        }
    }

