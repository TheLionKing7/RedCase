"""Legal Assistant endpoints — Addendum §7.2, the per-user conversational agent.

  POST /v1/assistant/threads                       create a thread
  POST /v1/assistant/threads/{id}/messages         send a message (SSE stream)
  POST /v1/assistant/threads/{id}/feedback         record feedback (learning signal)
  GET  /v1/assistant/threads/{id}                 the thread + turns + digest

Gated by require_feature("workbench.assistant") — the §7.2 Workbench premium seat
(the same per-seat surface as workbench.chat / workbench.analyze). Per-user RLS
(tenant + user) is enforced in SQL.

SSE stream: each turn emits a lightweight `agent_step` event per tool use and one
`assistant_reply` event carrying the final grounded answer. The reply is ALSO persisted
(assistant_messages) so the client can recover it via GET if the stream drops.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.assistant.service import MAX_TOOL_ITERATIONS, run_assistant_turn
from app.deps import TenantContext, get_tenant_context
from app.entitlements import require_feature
from app.middleware.zdr import get_logger

log = get_logger("redcase.assistant.api")

router = APIRouter(prefix="/v1/assistant", tags=["assistant"])


class ThreadCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class ThreadCreated(BaseModel):
    thread_id: str


class MessageSend(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


class FeedbackCreate(BaseModel):
    message_id: str
    rating: str = Field(pattern="^(UP|DOWN)$")
    correction_text: str | None = None


class FeedbackDone(BaseModel):
    feedback_id: str


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/threads", response_model=ThreadCreated)
async def create_thread(
    body: ThreadCreate,
    _: None = Depends(require_feature("workbench.assistant")),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> ThreadCreated:
    thread_id = uuid.uuid4()
    await ctx.db.execute(
        "INSERT INTO assistant_threads (id, tenant_id, created_by, title)"
        " VALUES ($1, $2, $3, $4)",
        thread_id,
        uuid.UUID(ctx.tenant_id),
        ctx.user_ref,
        (body.title or "Untitled thread")[:200],
    )
    log.info("assistant_thread_created", thread_id=str(thread_id), tenant_id=ctx.tenant_id)
    return ThreadCreated(thread_id=str(thread_id))


@router.get("/threads/{thread_id}")
async def get_thread(
    thread_id: str,
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> dict[str, Any]:
    thread = await ctx.db.fetchrow(
        "SELECT id, title, created_at, updated_at FROM assistant_threads"
        " WHERE id = $1::uuid",
        thread_id,
    )
    if thread is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="thread not found")
    msgs = await ctx.db.fetch(
        "SELECT id, role, content, citations, tool_uses, serving_provider,"
        " serving_model, created_at FROM assistant_messages"
        " WHERE thread_id = $1::uuid ORDER BY created_at",
        uuid.UUID(thread_id),
    )
    turns = []
    for r in msgs:
        turns.append(
            {
                "message_id": str(r["id"]),
                "role": r["role"],
                "content": r["content"],
                "citations": _json(r["citations"]),
                "tool_uses": _json(r["tool_uses"]),
                "serving_provider": r["serving_provider"],
                "serving_model": r["serving_model"],
                "created_at": r["created_at"].isoformat(),
            }
        )
    return {
        "thread_id": str(thread["id"]),
        "title": thread["title"],
        "created_at": thread["created_at"].isoformat(),
        "digest": await _digest(ctx),
        "turns": turns,
    }

@router.post("/threads/{thread_id}/messages")
async def send_message(
    thread_id: str,
    body: MessageSend,
    request: Request,
    _: None = Depends(require_feature("workbench.assistant")),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> StreamingResponse:
    thread = await ctx.db.fetchrow(
        "SELECT id FROM assistant_threads WHERE id = $1::uuid", thread_id
    )
    if thread is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="thread not found")
    settings = request.app.state.settings

    async def _stream():
        yield _sse({"event": "turn_started", "max_iterations": MAX_TOOL_ITERATIONS})
        reply = await run_assistant_turn(
            thread_id=thread_id,
            message_text=body.message,
            db=ctx.db,
            tenant_id=ctx.tenant_id,
            user_ref=ctx.user_ref,
            clearance=ctx.clearance,
            settings=settings,
        )
        for use in reply.tool_uses:
            yield _sse({"event": "agent_step", "tool": use})
        yield _sse(
            {
                "event": "assistant_reply",
                "content": reply.content,
                "citations": reply.citations,
                "refusal": reply.refusal,
                "serving_provider": reply.serving_provider,
                "serving_model": reply.serving_model,
            }
        )
        yield _sse({"event": "turn_done"})

    return StreamingResponse(_stream(), media_type="text/event-stream")


@router.post("/threads/{thread_id}/feedback", response_model=FeedbackDone)
async def submit_feedback(
    thread_id: str,
    body: FeedbackCreate,
    _: None = Depends(require_feature("workbench.assistant")),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> FeedbackDone:
    # RLS confines feedback to the caller's own thread + message.
    owned = await ctx.db.fetchrow(
        "SELECT 1 FROM assistant_messages"
        " WHERE id = $1::uuid AND thread_id = $2::uuid",
        uuid.UUID(body.message_id),
        uuid.UUID(thread_id),
    )
    if owned is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="message not found")
    feedback_id = uuid.uuid4()
    await ctx.db.execute(
        "INSERT INTO assistant_feedback (id, tenant_id, thread_id, message_id, user_ref,"
        " rating, correction_text) VALUES ($1, $2, $3, $4, $5, $6, $7)",
        feedback_id,
        uuid.UUID(ctx.tenant_id),
        uuid.UUID(thread_id),
        uuid.UUID(body.message_id),
        ctx.user_ref,
        body.rating,
        body.correction_text,
    )
    # Learning mechanism (2): a structured correction is folded into the preference
    # profile immediately, so the NEXT turn surfaces it.
    if body.rating == "DOWN" and body.correction_text:
        await _apply_correction_preference(
            ctx, thread_id, body.message_id, body.correction_text
        )
    return FeedbackDone(feedback_id=str(feedback_id))


async def _apply_correction_preference(
    ctx: TenantContext, thread_id: str, message_id: str, correction: str
) -> None:
    """Insert a `style_correction` preference from a DOWN vote's correction text
    (source CORRECTION) so the next turn surfaces it in the prompt."""
    await ctx.db.execute(
        "INSERT INTO assistant_preferences (tenant_id, user_ref, pref_key, pref_value, source)"
        " VALUES ($1, $2, 'style_correction', $3::jsonb, 'CORRECTION')",
        uuid.UUID(ctx.tenant_id),
        ctx.user_ref,
        json.dumps(
            {"text": correction[:1000], "thread_id": thread_id, "message_id": message_id}
        ),
    )
    log.info("assistant_feedback_preference", thread_id=thread_id, tenant_id=ctx.tenant_id)


async def _digest(ctx: TenantContext) -> dict[str, Any]:
    """Per-user workspace digest built from EXISTING tables (matters, invoices,
    analyses). ZDR: ids, counts, statuses only."""
    matters = await ctx.db.fetchrow(
        "SELECT COUNT(*) AS total,"
        " COUNT(*) FILTER (WHERE status = 'ACTIVE') AS active"
        " FROM matters WHERE tenant_id = $1::uuid",
        uuid.UUID(ctx.tenant_id),
    )
    analyses = await ctx.db.fetchrow(
        "SELECT COUNT(*) FILTER (WHERE status IN ('RUNNING','NEEDS_REVIEW')) AS in_flight,"
        " COUNT(*) AS total FROM document_analyses WHERE created_by = $1",
        ctx.user_ref,
    )
    unpaid = await ctx.db.fetchval(
        "SELECT COALESCE(SUM(i.amount_ngn - COALESCE(p.paid, 0)), 0)"
        " FROM (SELECT id, amount_ngn FROM invoices"
        " WHERE tenant_id = $1::uuid AND status NOT IN ('PAID','WRITTEN_OFF')) i"
        " LEFT JOIN (SELECT invoice_id, SUM(amount_ngn) AS paid FROM payments"
        " GROUP BY invoice_id) p ON p.invoice_id = i.id",
        uuid.UUID(ctx.tenant_id),
    )
    return {
        "active_matters": int(matters["active"] or 0),
        "total_matters": int(matters["total"] or 0),
        "in_flight_analyses": int(analyses["in_flight"] or 0),
        "unpaid_amount_ngn": float(unpaid or 0.0),
    }


def _json(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else (v or [])

