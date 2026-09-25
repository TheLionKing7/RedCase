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
    is_archived: bool
    created_at: str


async def _resolve_channel(ctx: TenantContext, channel_id: str) -> None:
    """404 unless the caller can SEE the channel (RLS can_read_channel)."""
    visible = await ctx.db.fetchval(
        "SELECT id FROM channels WHERE id = $1::uuid", channel_id
    )
    if visible is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="channel not found")


async def _handle_time_command(
    ctx: TenantContext, channel_id: str, raw: str, idempotency_key: str | None
) -> None:
    """Parse `/time <minutes> <description>` and record a time entry on the
    channel's matter. Only valid in MATTER channels (the time attaches to the
    matter); FIRM/DIRECT channels have no matter to bill."""
    tokens = raw.lstrip()[len("/time") :].strip().split(None, 1)
    if not tokens or not tokens[0].isdigit():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="/time <minutes> <description> — e.g. `/time 30 reviewed affidavit`",
        )
    minutes = int(tokens[0])
    description = tokens[1].strip() if len(tokens) > 1 else "time entry"
    if minutes <= 0:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="minutes must be positive"
        )
    matter = await ctx.db.fetchval(
        "SELECT matter_id FROM channels WHERE id = $1::uuid AND kind = 'MATTER'",
        uuid.UUID(channel_id),
    )
    if matter is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="/time is only valid in a matter channel",
        )
    await ctx.db.execute(
        "INSERT INTO time_entries"
        " (tenant_id, matter_id, user_ref, description, minutes, idempotency_key)"
        " VALUES ($1, $2, $3, $4, $5, $6)"
        " ON CONFLICT (tenant_id, idempotency_key) DO NOTHING",
        uuid.UUID(ctx.tenant_id),
        matter,
        ctx.user_ref,
        description,
        minutes,
        idempotency_key,
    )


@router.post("/channels/{channel_id}/messages", status_code=201)
async def post_message(
    channel_id: str,
    body: MessageCreate,
    _: None = Depends(require_feature("comms.send")),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> MessageCreated:
    await _resolve_channel(ctx, channel_id)
    archived = await ctx.db.fetchval(
        "SELECT m.status IN ('CONCLUDED', 'ARCHIVED') "
        "FROM channels c JOIN matters m ON m.id = c.matter_id "
        "WHERE c.id = $1::uuid AND c.kind = 'MATTER'",
        uuid.UUID(channel_id),
    )
    if archived:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Concluded matter channels are read-only.")

    # Slash-command surface — time capture where work happens (§9.1): a
    # `/time 30 reviewed affidavit` in a matter channel records a time entry on
    # that channel's matter instead of a free-text message.
    if body.body.lstrip().startswith("/time"):
        await _handle_time_command(ctx, channel_id, body.body, body.idempotency_key)
        # Reflect the capture back into the channel as a normal message so the
        # matter thread has a durable record of who logged what.
        key = body.idempotency_key
        row = await ctx.db.fetchrow(
            "INSERT INTO channel_messages"
            " (tenant_id, channel_id, sender_ref, sender_kind, body, idempotency_key)"
            " VALUES ($1, $2, $3, 'USER', $4, $5)"
            " ON CONFLICT (tenant_id, idempotency_key) DO NOTHING"
            " RETURNING id, created_at",
            uuid.UUID(ctx.tenant_id),
            uuid.UUID(channel_id),
            ctx.user_ref,
            f"⏱ logged {body.body.lstrip()[len('/time'):].strip()}",
            key,
        )
        if row is None:
            row = await ctx.db.fetchrow(
                "SELECT id, created_at FROM channel_messages"
                " WHERE tenant_id = $1::uuid AND idempotency_key = $2"
                "   AND channel_id = $3::uuid",
                uuid.UUID(ctx.tenant_id),
                key,
                uuid.UUID(channel_id),
            )
        log.info(
            "channel_time_command",
            channel_id=channel_id,
            sender=ctx.user_ref,
        )
        return MessageCreated(
            id=str(row["id"]),
            channel_id=channel_id,
            created_at=row["created_at"].isoformat(),
        )

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
        "SELECT c.id, c.name, c.kind, c.matter_id, c.created_at, "
        "       (c.kind = 'MATTER' AND m.status IN ('CONCLUDED', 'ARCHIVED')) AS is_archived "
        "FROM channels c LEFT JOIN matters m ON m.id = c.matter_id "
        "ORDER BY c.created_at"
    )
    return [
        ChannelRead(
            id=str(r["id"]),
            name=r["name"],
            kind=r["kind"],
            matter_id=str(r["matter_id"]) if r["matter_id"] else None,
            is_archived=bool(r["is_archived"]),
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


@router.get("/channels/unread-count")
async def direct_unread_count(
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> dict[str, int]:
    """Count incoming direct messages after this user's last-read cursor."""
    count = await ctx.db.fetchval(
        "SELECT count(*) FROM channels c"
        " JOIN channel_participants cp ON cp.channel_id = c.id"
        " LEFT JOIN channel_read_state rs ON rs.tenant_id = c.tenant_id"
        "   AND rs.channel_id = c.id AND rs.user_ref = $2"
        " JOIN channel_messages m ON m.channel_id = c.id"
        " WHERE c.tenant_id = $1::uuid AND c.kind = 'DIRECT'"
        "   AND cp.participant_ref = $2 AND m.sender_ref <> $2"
        "   AND m.created_at > COALESCE(rs.last_read_at, 'epoch'::timestamptz)",
        uuid.UUID(ctx.tenant_id),
        ctx.user_ref,
    )
    return {"unread_count": int(count or 0)}


@router.post("/channels/{channel_id}/read", status_code=204)
async def mark_channel_read(
    channel_id: str,
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> None:
    """Advance a user's read cursor only for a channel visible to that user."""
    await _resolve_channel(ctx, channel_id)
    await ctx.db.execute(
        "INSERT INTO channel_read_state (tenant_id, channel_id, user_ref, last_read_at)"
        " VALUES ($1::uuid, $2::uuid, $3, now())"
        " ON CONFLICT (tenant_id, channel_id, user_ref)"
        " DO UPDATE SET last_read_at = now()",
        uuid.UUID(ctx.tenant_id),
        uuid.UUID(channel_id),
        ctx.user_ref,
    )


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
