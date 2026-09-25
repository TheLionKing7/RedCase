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
from datetime import UTC, datetime
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
    document_id: uuid.UUID | None = None
    brief_name: str | None = Field(default=None, min_length=1, max_length=300)
    grantee_ref: str | None = Field(default=None, max_length=200)
    grant_level: str = Field(default="READ")
    reason: str | None = Field(default=None, max_length=1000)


class AccessDecisionIn(BaseModel):
    approve: bool
    grant_level: str | None = Field(default=None)
    expires_at: datetime | None = None
    grantee_ref: str | None = Field(default=None, min_length=1, max_length=200)


@router.get("/access-requests")
async def my_access_requests(
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> dict[str, Any]:
    """The caller's requests: what they asked for, and what awaits their decision."""
    rows = await ctx.db.fetch(
        """
        SELECT ar.id, ar.document_id, ar.requester_ref, ar.grantee_ref, ar.grant_level, ar.reason,
               ar.status, ar.decided_by, ar.decided_at, ar.created_at,
               COALESCE(d.case_title, ar.requested_title) AS brief_name
        FROM access_requests ar LEFT JOIN documents d ON d.id = ar.document_id
        WHERE ar.tenant_id = $1::uuid
          AND (ar.requester_ref = $2 OR ar.grantee_ref = $2 OR $3)
        ORDER BY ar.created_at DESC
        """,
        uuid.UUID(ctx.tenant_id),
        ctx.user_ref,
        ctx.clearance in DECIDERS,
    )
    return {"requests": [_wire_row(r) for r in rows]}


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
    if body.document_id is None and not (body.brief_name and body.brief_name.strip()):
        raise HTTPException(422, "Brief name is required.")
    if body.document_id is None:
        existing_document = await ctx.db.fetchval(
            "SELECT d.id FROM documents d JOIN vaults v ON v.id = d.vault_id"
            " WHERE d.tenant_id = $1::uuid AND v.vault_type = 'firm'"
            " AND lower(d.case_title) = lower($2) LIMIT 1",
            uuid.UUID(ctx.tenant_id), body.brief_name.strip(),
        )
        saved = await ctx.db.fetchrow(
            "INSERT INTO access_requests"
            " (tenant_id, document_id, requester_ref, grantee_ref, grant_level, reason,"
            " requested_title)"
            " VALUES ($1, NULL, $2, $2, 'READ', $3, $4)"
            " RETURNING id, document_id, requester_ref, grantee_ref, grant_level, reason,"
            " status, created_at, requested_title AS brief_name",
            uuid.UUID(ctx.tenant_id), ctx.user_ref, body.reason, body.brief_name.strip(),
        )
        if existing_document:
            await ctx.db.execute(
                "UPDATE access_requests SET document_id = $1 WHERE id = $2::uuid",
                existing_document,
                saved["id"],
            )
            saved = await ctx.db.fetchrow(
                "SELECT id, document_id, requester_ref, grantee_ref, grant_level, reason,"
                " status, created_at, requested_title AS brief_name"
                " FROM access_requests WHERE id = $1::uuid",
                saved["id"],
            )
        return {"request": _wire_row(saved)}
    if body.grantee_ref is None:
        raise HTTPException(422, "grantee_ref is required for document-ID requests.")
    document_id = body.document_id
    row = await ctx.db.fetchrow(
        """
        INSERT INTO access_requests
            (tenant_id, document_id, requester_ref, grantee_ref, grant_level, reason)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id, document_id, requester_ref, grantee_ref, grant_level, reason,
                  status, created_at
        """,
        uuid.UUID(ctx.tenant_id),
        document_id,
        ctx.user_ref,
        body.grantee_ref or ctx.user_ref,
        body.grant_level,
        body.reason,
    )
    log.info(
        "access_request_created",
        tenant_id=ctx.tenant_id,
        document_id=str(document_id),
        grantee_ref=body.grantee_ref or ctx.user_ref,
    )
    return {"request": _wire_row(row)}


def _wire_row(row) -> dict[str, Any]:
    data = dict(row)
    for key in ("created_at", "decided_at"):
        if data.get(key) is not None:
            data[key] = data[key].isoformat()
    return data


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
        "SELECT id, document_id, requested_title, grantee_ref, requester_ref, grant_level, status"
        " FROM access_requests WHERE id = $1::uuid AND tenant_id = $2::uuid",
        request_id,
        uuid.UUID(ctx.tenant_id),
    )
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Request not found.")
    if req["status"] != "PENDING":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Request already decided.")
    grantee_ref = body.grantee_ref or req["grantee_ref"]
    document_id = req["document_id"]
    if body.approve and document_id is None:
        document_id = await ctx.db.fetchval(
            "SELECT d.id FROM documents d JOIN vaults v ON v.id = d.vault_id"
            " WHERE d.tenant_id = $1::uuid AND v.vault_type = 'firm'"
            " AND lower(d.case_title) = lower($2) LIMIT 1",
            uuid.UUID(ctx.tenant_id), req["requested_title"],
        )
        if document_id is None:
            raise HTTPException(404, "No Internal Brief currently matches this request.")
    if req["requester_ref"] == ctx.user_ref and grantee_ref == ctx.user_ref:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "A requester cannot approve their own access request.",
        )
    if grantee_ref == ctx.user_ref:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="A decider may not approve a grant to themselves - need a second principal.",
        )
    level = body.grant_level or req["grant_level"] or "READ"
    expires_at = body.expires_at
    if body.approve and expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            raise HTTPException(422, "Grant expiry must be in the future.")
    if body.grantee_ref is not None and body.grantee_ref != req["grantee_ref"]:
        member_exists = await ctx.db.fetchval(
            "SELECT 1 FROM firm_members WHERE tenant_id = $1::uuid AND user_ref = $2",
            uuid.UUID(ctx.tenant_id), body.grantee_ref,
        )
        if not member_exists:
            raise HTTPException(422, "The selected user is not a member of this firm.")
    async with ctx.db.transaction():
        if body.approve:
            await ctx.db.execute(
                """
            INSERT INTO document_grants
                    (tenant_id, document_id, user_ref, grant_level, granted_by, expires_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                uuid.UUID(ctx.tenant_id),
                document_id,
                grantee_ref,
                level,
                ctx.user_ref,
                expires_at,
            )
        await ctx.db.execute(
            "UPDATE access_requests SET document_id = COALESCE($4, document_id),"
            " status = $1, decided_by = $2, decided_at = now()"
            " WHERE id = $3::uuid",
            "APPROVED" if body.approve else "DENIED",
            ctx.user_ref,
            request_id,
            document_id,
        )
    log.info(
        "access_request_decided",
        tenant_id=ctx.tenant_id,
        request_id=str(request_id),
        approve=body.approve,
        decided_by=ctx.user_ref,
    )
    return {"status": "APPROVED" if body.approve else "DENIED"}


@router.get("/access-grants")
async def my_access_grants(
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> dict[str, Any]:
    rows = await ctx.db.fetch(
        "SELECT g.id, g.document_id, d.case_title AS brief_name, g.granted_at,"
        " g.expires_at, g.relinquished_at, g.grant_level"
        " FROM document_grants g JOIN documents d ON d.id = g.document_id"
        " WHERE g.tenant_id = $1::uuid AND g.user_ref = $2"
        " ORDER BY g.granted_at DESC",
        uuid.UUID(ctx.tenant_id), ctx.user_ref,
    )
    return {
        "grants": [
            {
                **dict(r),
                "granted_at": (
                    r["granted_at"].isoformat() if r["granted_at"] else None
                ),
                "expires_at": (
                    r["expires_at"].isoformat() if r["expires_at"] else None
                ),
                "relinquished_at": (
                    r["relinquished_at"].isoformat()
                    if r["relinquished_at"]
                    else None
                ),
            }
            for r in rows
        ]
    }


@router.post("/access-grants/{grant_id}/relinquish")
async def relinquish_grant(
    grant_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> dict[str, Any]:
    changed = await ctx.db.fetchval(
        "SELECT relinquish_document_grant($1::uuid)", grant_id
    )
    if not changed:
        raise HTTPException(404, "Active grant not found.")
    return {"status": "RELINQUISHED"}
