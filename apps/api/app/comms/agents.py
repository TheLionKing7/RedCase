"""Functional-agent channel posts (Feature-Addendum §7.2).

Functional agents never converse. They POST labeled results (battle cards,
alerts) as AGENT/SYSTEM channel messages with analysis_id/document_id refs —
never in reply to a mention, never an omnibus bot persona, never an
agent-to-agent loop. The only conversational agent is the per-user Legal
Assistant (workbench Expert Chat), which does NOT surface in channels.

Loop guard (enforced here): an agent may not thread its post under another
AGENT/SYSTEM message. Sharing an analysis into a channel is a USER act, not an
agent act — the user posts through POST /v1/channels/{id}/messages with an
analysis_id; this module is only for worker-posted results.

ZDR: posts reference documents/analyses by id; they never carry document
content, and no document text enters logs.
"""

import uuid

import asyncpg

from app.middleware.zdr import get_logger

log = get_logger("redcase.comms.agents")


class AgentPostError(ValueError):
    """A functional-agent post violates the §7.2 contract."""


async def post_agent_message(
    db: asyncpg.Connection,
    tenant_id: str,
    channel_id: str,
    agent_ref: str,
    body: str,
    *,
    sender_kind: str = "AGENT",
    analysis_id: str | None = None,
    document_id: str | None = None,
    thread_id: str | None = None,
) -> dict:
    """Post a functional-agent result to a channel as AGENT/SYSTEM.

    Runs inside its own transaction with the agent's identity set as the RLS
    GUC (app.tenant_id + app.user_ref = agent_ref), so the per-participant
    send policy authorizes the post when the agent is registered in
    channel_participants. Rejects: a non-AGENT/SYSTEM kind, an empty body, a
    reference outside the tenant (ref integrity), and a thread under an
    agent/system message (loop guard).
    """
    if sender_kind not in ("AGENT", "SYSTEM"):
        raise AgentPostError("sender_kind must be AGENT or SYSTEM")
    if not body or not body.strip():
        raise AgentPostError("empty agent body")

    async with db.transaction():
        await db.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_id)
        await db.execute("SELECT set_config('app.user_ref', $1, true)", agent_ref)

        # Loop guard: an agent may not reply under an agent/system message.
        if thread_id is not None:
            parent_kind = await db.fetchval(
                "SELECT sender_kind FROM channel_messages"
                " WHERE id = $1::uuid AND tenant_id = $2::uuid",
                uuid.UUID(thread_id),
                uuid.UUID(tenant_id),
            )
            if parent_kind is None:
                raise AgentPostError("thread parent not found in this tenant")
            if parent_kind in ("AGENT", "SYSTEM"):
                raise AgentPostError(
                    "agent may not reply to an agent/system message (loop guard)"
                )

        # Ref integrity: channel + any refs must exist in this tenant.
        channel = await db.fetchval(
            "SELECT id FROM channels WHERE id = $1::uuid AND tenant_id = $2::uuid",
            uuid.UUID(channel_id),
            uuid.UUID(tenant_id),
        )
        if channel is None:
            raise AgentPostError("channel not found in this tenant")
        if analysis_id is not None:
            a = await db.fetchval(
                "SELECT id FROM document_analyses"
                " WHERE id = $1::uuid AND tenant_id = $2::uuid",
                uuid.UUID(analysis_id),
                uuid.UUID(tenant_id),
            )
            if a is None:
                raise AgentPostError("analysis not found in this tenant")
        if document_id is not None:
            d = await db.fetchval(
                "SELECT id FROM documents WHERE id = $1::uuid AND tenant_id = $2::uuid",
                uuid.UUID(document_id),
                uuid.UUID(tenant_id),
            )
            if d is None:
                raise AgentPostError("document not found in this tenant")

        row = await db.fetchrow(
            "INSERT INTO channel_messages"
            " (tenant_id, channel_id, sender_ref, sender_kind, body, thread_id,"
            "  document_id, analysis_id)"
            " VALUES ($1, $2, $3, $4, $5, $6, $7, $8)"
            " RETURNING id, created_at",
            uuid.UUID(tenant_id),
            uuid.UUID(channel_id),
            agent_ref,
            sender_kind,
            body,
            uuid.UUID(thread_id) if thread_id else None,
            uuid.UUID(document_id) if document_id else None,
            uuid.UUID(analysis_id) if analysis_id else None,
        )

    log.info(
        "agent_post",
        channel_id=channel_id,
        agent=agent_ref,
        kind=sender_kind,
        has_analysis=analysis_id is not None,
        has_document=document_id is not None,
    )
    return {
        "id": str(row["id"]),
        "channel_id": channel_id,
        "sender_kind": sender_kind,
        "created_at": row["created_at"].isoformat(),
    }
