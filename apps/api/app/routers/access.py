"""Access-request flow — IA spec §1.6 (S10-4).

  GET  /v1/access-requests                my requests (as requester or grantor-decider)
  POST /v1/access-requests              request a document grant (self-service privilege)
  POST /v1/access-requests/{id}/decide  approve/deny (PARTNER/ADMIN only, never self)

#1.6 is the privilege model's self-service layer: a user requests a named grant on a named
document; a licensed senior reviewer (PARTNER/ADMIN — never the requester) either grants
(writing a document_grants row, the real ACL from 0008) or denies. The request row
itself never grants anything. No admin begging, no widening of clearance bands.

ZDR: requests carry only short operational text (requester_ref, grantee_ref, grant_level,
reason). All paths are tenant-scoped via the RLS connection from get_tenant_context.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.deps import TenantContext, get_tenant_context
from app.middleware.zdr import get_logger

log = get_logger("redcase.access")

router = APIRouter(prefix="/v1", tags=["access-requests"])

DECIDERS = ("PARTNER", "ADMIN")
GRANT_LEVELS = ("READ", "ANNOTATE")


class AccessRequestIn(BaseModel):
    document_id: uuid.UUID
    grantee_ref: str = Field(min_length=1, max_length=200)
    grant_level: str = Field(default="READ")
    reason: str | None = Field(default=None, max_length=1000)


class AccessDecisionIn(BaseModel):
    approve: bool
    grant_level: str | None = Field(default=None)


@router.get("/access-requests")
async def my_access_requests(
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> dict[str, Any]:
    """The caller's requests: what they asked for, and what awaits their decision."""
    rows = await ctx.db.fetch(
        """
        SELECT id, document_id, requester_ref, grantee_ref, grant_level, reason,
               status, decided_by, decided_at, created_at
        FROM access_requests
        WHERE tenant_id = $1::uuid
          AND (requester_ref = $2 OR grantee_ref = $2 OR $3)
        ORDER BY created_at DESC
        """,
        uuid.UUID(ctx.tenant_id),
        ctx.user_ref,
        ctx.clearance in DECIDERS,
    )
    return {"requests": [dict(r) for r in rows]}


@router.post("/access-requests", status_code=201)
async def create_access_request(
    body: AccessRequestIn,
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> dict[str, Any]:
    """Self-service privilege request (#1.6). Never grants — a senior reviewer decides."""
    if body.grant_level not in GRANT_LEVELS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"grant_level must be one of {', '.join(GRANT_LEVELS)}",
        )
    if ctx.clearance in DECIDERS and body.grantee_ref == ctx.user_ref:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="A senior reviewer already holds access — no request needed.",
        )
    row = await ctx.db.fetchrow(
        """
        INSERT INTO access_requests
            (tenant_id, document_id, requester_ref, grantee_ref, grant_level, reason)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id, document_id, requester_ref, grantee_ref, grant_level, reason,
                  status, created_at
        """,
        uuid.UUID(ctx.tenant_id),
        body.document_id,
        ctx.user_ref,
        body.grantee_ref,
        body.grant_level,
        body.reason,
    )
    log.info(
        "access_request_created",
        tenant_id=ctx.tenant_id,
        document_id=str(body.document_id),
        grantee_ref=body.grantee_ref,
    )
    return {"request": dict(row)}


@router.post("/access-requests/{request_id}/decide")
async def decide_access_request(
    request_id: uuid.UUID,
    body: AccessDecisionIn,
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> dict[str, Any]:
    """Approve (writes the real ACL grant, #1.6) or deny. PARTNER/ADMIN only."""
    if ctx.clearance not in DECIDERS:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Only PARTNER/ADMIN clearances may decide access requests.",
        )
    req = await ctx.db.fetchrow(
        "SELECT id, document_id, grantee_ref, grant_level, status"
        " FROM access_requests WHERE id = $1::uuid AND tenant_id = $2::uuid",
        request_id,
        uuid.UUID(ctx.tenant_id),
    )
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Request not found.")
    if req["status"] != "PENDING":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Request already decided.")
    if req["grantee_ref"] == ctx.user_ref:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="A decider may not approve a grant to themselves - need a second principal.",
        )
    level = body.grant_level or req["grant_level"] or "READ"
    async with ctx.db.transaction():
        if body.approve:
            await ctx.db.execute(
                """
                INSERT INTO document_grants
                    (tenant_id, document_id, user_ref, grant_level, granted_by)
                VALUES ($1, $2, $3, $4, $5)
                """,
                uuid.UUID(ctx.tenant_id),
                req["document_id"],
                req["grantee_ref"],
                level,
                ctx.user_ref,
            )
        await ctx.db.execute(
            "UPDATE access_requests SET status = $1, decided_by = $2, decided_at = now()"
            " WHERE id = $3::uuid",
            "APPROVED" if body.approve else "DENIED",
            ctx.user_ref,
            request_id,
        )
    log.info(
        "access_request_decided",
        tenant_id=ctx.tenant_id,
        request_id=str(request_id),
        approve=body.approve,
        decided_by=ctx.user_ref,
    )
    return {"status": "APPROVED" if body.approve else "DENIED"}
