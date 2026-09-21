"""Firm communication channels — Feature-Addendum §7 (Core tier, no UI yet).

  POST /v1/channels/{id}/messages   body {body, thread_id?, document_id?,
                                         analysis_id?} → 201 {id, ...}

Posting is entitlement-gated (require_feature("comms.send") — a CORE
feature, so the gate always ALLOWs but still writes its entitlement_events
DECISION row). Every query is RLS-scoped via the tenant context, and
attachment references are validated against the tenant —
FK constraints are not RLS-aware, so an unvalidated insert could pin a
message to another tenant's document/analysis/thread.

ZDR (§7 rule): messages reference document_id/analysis_id; they never
hold document content, and no document text enters logs.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.deps import TenantContext, get_tenant_context
from app.entitlements import require_feature
from app.middleware.zdr import get_logger

log = get_logger("redcase.channels")

router = APIRouter(prefix="/v1", tags=["channels"])


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    thread_id: str | None = None
    document_id: str | None = None
    analysis_id: str | None = None
    idempotency_key: str | None = None


class MessageCreated(BaseModel):
    id: str
    channel_id: str
    created_at: str


class MessageRead(BaseModel):
    id: str
    channel_id: str
    sender_ref: str
    sender_kind: str
    body: str
    thread_id: str | None
    document_id: str | None
    analysis_id: str | None
    created_at: str


class ChannelRead(BaseModel):
    id: str
    name: str
    kind: str
    matter_id: str | None
    created_at: str


async def _resolve_channel(ctx: TenantContext, channel_id: str) -> None:
    """404 unless the caller can SEE the channel (RLS can_read_channel)."""
    visible = await ctx.db.fetchval(
        "SELECT id FROM channels WHERE id = $1::uuid", channel_id
    )
    if visible is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="channel not found")


@router.post("/channels/{channel_id}/messages", status_code=201)
async def post_message(
    channel_id: str,
    body: MessageCreate,
    _: None = Depends(require_feature("comms.send")),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> MessageCreated:
    await _resolve_channel(ctx, channel_id)

    # Attachment reference checks — FKs bypass RLS, so verify tenancy
    # explicitly (§7: references only; no cross-tenant pinning).
    ref_checks: dict[str, tuple[str | None, str]] = {
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
    for label, (ref, sql) in ref_checks.items():
        if ref is None:
            continue
        visible = await ctx.db.fetchval(sql, uuid.UUID(ref), uuid.UUID(ctx.tenant_id))
        if visible is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"referenced {label} not found in this tenant",
            )

    key = body.idempotency_key
    row = await ctx.db.fetchrow(
        "INSERT INTO channel_messages"
        " (tenant_id, channel_id, sender_ref, sender_kind, body, thread_id,"
        "  document_id, analysis_id, idempotency_key)"
        " VALUES ($1, $2, $3, 'USER', $4, $5, $6, $7, $8)"
        " ON CONFLICT (tenant_id, idempotency_key) DO NOTHING"
        " RETURNING id, created_at",
        uuid.UUID(ctx.tenant_id),
        uuid.UUID(channel_id),
        ctx.user_ref,
        body.body,
        uuid.UUID(body.thread_id) if body.thread_id else None,
        uuid.UUID(body.document_id) if body.document_id else None,
        uuid.UUID(body.analysis_id) if body.analysis_id else None,
        key,
    )
    if row is None:
        # Idempotent retry: the message already exists — return it.
        row = await ctx.db.fetchrow(
            "SELECT id, created_at FROM channel_messages"
            " WHERE tenant_id = $1::uuid AND idempotency_key = $2"
            "   AND channel_id = $3::uuid",
            uuid.UUID(ctx.tenant_id),
            key,
            uuid.UUID(channel_id),
        )
        if row is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="idempotency_key already used for a different channel",
            )
    log.info(
        "channel_message",
        channel_id=channel_id,
        sender=ctx.user_ref,
        sender_kind="USER",
        has_document=body.document_id is not None,
        has_analysis=body.analysis_id is not None,
    )
    return MessageCreated(
        id=str(row["id"]),
        channel_id=channel_id,
        created_at=row["created_at"].isoformat(),
    )


@router.get("/channels", response_model=list[ChannelRead])
async def list_channels(
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> list[ChannelRead]:
    # RLS can_read_channel filters to participant/FIRM channels only.
    rows = await ctx.db.fetch(
        "SELECT id, name, kind, matter_id, created_at FROM channels"
        " ORDER BY created_at"
    )
    return [
        ChannelRead(
            id=str(r["id"]),
            name=r["name"],
            kind=r["kind"],
            matter_id=str(r["matter_id"]) if r["matter_id"] else None,
            created_at=r["created_at"].isoformat(),
        )
        for r in rows
    ]


@router.get("/channels/{channel_id}/messages", response_model=list[MessageRead])
async def list_messages(
    channel_id: str,
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> list[MessageRead]:
    await _resolve_channel(ctx, channel_id)
    # RLS participant_read filters to the caller's visible messages.
    rows = await ctx.db.fetch(
        "SELECT id, channel_id, sender_ref, sender_kind, body, thread_id,"
        " document_id, analysis_id, created_at"
        " FROM channel_messages WHERE channel_id = $1::uuid ORDER BY created_at",
        uuid.UUID(channel_id),
    )
    return [
        MessageRead(
            id=str(r["id"]),
            channel_id=str(r["channel_id"]),
            sender_ref=r["sender_ref"],
            sender_kind=r["sender_kind"],
            body=r["body"],
            thread_id=str(r["thread_id"]) if r["thread_id"] else None,
            document_id=str(r["document_id"]) if r["document_id"] else None,
            analysis_id=str(r["analysis_id"]) if r["analysis_id"] else None,
            created_at=r["created_at"].isoformat(),
        )
        for r in rows
    ]


class ChannelCreate(BaseModel):
    kind: str
    other_user_ref: str


@router.post("/channels", status_code=201)
async def create_channel(
    body: ChannelCreate,
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> dict:
    """Create a DIRECT channel between the caller and another user.

    Matter (#case-{a}-v-{b}) and FIRM (#general) channels are auto-provisioned
    by the system; the only user-created kind is DIRECT. provision_direct_channel
    is SECURITY DEFINER and adds both participants atomically.
    """
    if body.kind != "DIRECT":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="only DIRECT channels are user-created (matter/firm are auto-provisioned)",
        )
    if not body.other_user_ref or not body.other_user_ref.strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="other_user_ref required"
        )
    channel_id = await ctx.db.fetchval(
        "SELECT provision_direct_channel($1::uuid, $2, $3)",
        uuid.UUID(ctx.tenant_id),
        ctx.user_ref,
        body.other_user_ref,
    )
    log.info("channel_created", kind="DIRECT", channel_id=str(channel_id))
    return {"id": str(channel_id), "kind": "DIRECT"}
