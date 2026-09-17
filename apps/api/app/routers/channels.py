"""Firm communication channels — Feature-Addendum §7 (Core tier, no UI yet).

  POST /v1/channels/{id}/messages   body {body, thread_id?, document_id?,
                                         analysis_id?} → 201 {id, ...}

Channels are Core tier: posting is NOT entitlement-gated (§6 gates only
generative features), but every query is RLS-scoped via the tenant
context, and attachment references are validated against the tenant —
FK constraints are not RLS-aware, so an unvalidated insert could pin a
message to another tenant's document/analysis/thread.

ZDR (§7 rule): messages reference document_id/analysis_id; they never
hold document content, and no document text enters logs.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.deps import TenantContext, get_tenant_context
from app.middleware.zdr import get_logger

log = get_logger("redcase.channels")

router = APIRouter(prefix="/v1", tags=["channels"])


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    thread_id: str | None = None
    document_id: str | None = None
    analysis_id: str | None = None


class MessageCreated(BaseModel):
    id: str
    channel_id: str
    created_at: str


@router.post("/channels/{channel_id}/messages", status_code=201)
async def post_message(
    channel_id: str,
    body: MessageCreate,
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> MessageCreated:
    # Channel visibility: RLS scopes the fetch to this tenant.
    channel = await ctx.db.fetchval(
        "SELECT id FROM channels WHERE id = $1::uuid", channel_id
    )
    if channel is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="channel not found in this tenant",
        )

    # Attachment reference checks — FKs bypass RLS, so verify tenancy
    # explicitly (§7: references only; no cross-tenant pinning).
    REF_CHECKS: dict[str, tuple[str, str]] = {
        "thread": (
            body.thread_id,
            "SELECT id FROM channel_messages WHERE id = $1::uuid AND tenant_id = $2::uuid",
        ),
        "document": (
            body.document_id,
            "SELECT id FROM documents WHERE id = $1::uuid AND tenant_id = $2::uuid",
        ),
        "analysis": (
            body.analysis_id,
            "SELECT id FROM document_analyses WHERE id = $1::uuid AND tenant_id = $2::uuid",
        ),
    }
    for label, (ref, sql) in REF_CHECKS.items():
        if ref is None:
            continue
        visible = await ctx.db.fetchval(sql, uuid.UUID(ref), uuid.UUID(ctx.tenant_id))
        if visible is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"referenced {label} not found in this tenant",
            )

    row = await ctx.db.fetchrow(
        "INSERT INTO channel_messages"
        " (tenant_id, channel_id, sender_ref, body, thread_id, document_id,"
        "  analysis_id)"
        " VALUES ($1, $2, $3, $4, $5, $6, $7)"
        " RETURNING id, created_at",
        uuid.UUID(ctx.tenant_id),
        uuid.UUID(channel_id),
        ctx.user_ref,
        body.body,
        uuid.UUID(body.thread_id) if body.thread_id else None,
        uuid.UUID(body.document_id) if body.document_id else None,
        uuid.UUID(body.analysis_id) if body.analysis_id else None,
    )
    log.info(
        "channel_message",
        channel_id=channel_id,
        sender=ctx.user_ref,
        has_document=body.document_id is not None,
        has_analysis=body.analysis_id is not None,
    )
    return MessageCreated(
        id=str(row["id"]),
        channel_id=channel_id,
        created_at=row["created_at"].isoformat(),
    )
