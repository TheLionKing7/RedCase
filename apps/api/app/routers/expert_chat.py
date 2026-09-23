"""Expert Chat — the per-user Legal Assistant (Addendum §3.2, Step D).

DEPRECATED (M1 consolidation, see docs/RedCase-Codebase-Audit.md §M1): this
"analysis-scoped chat" surface is SUPERSEDED by the general per-user agent in
``app/assistant/`` (Addendum §7.2), which is the ONE conversational surface.
The assistant already drills into the caller's own complete analyses via its analysis
tools (``show_overview`` / ``show_arguments`` / ``show_similar_cases`` /
``show_law``). Do not add features here. Existing routes stay mounted for backward
compatibility; new chat work goes in ``app/assistant/service.py``. Threads are
migrated to the assistant's ``assistant_threads``/``assistant_messages`` at the
next data-migration window.

Historical contract: this surface was "grounded in the caller's own analysis + both
vaults", reusing the answer_question grounding contract (citation verification,
refusal, serving-provider audit). Chat messages reused query_audit (thread_id +
analysis_id columns) — append-only. ZDR: the question is stored as a SHA-256
hash, never the question text.

  POST /v1/analyses/{id}/chat   body {question} → grounded answer
  GET  /v1/analyses/{id}/chat   → the thread's turns (audit rows)

Entitlement: require_feature("workbench.chat").
"""

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.deps import TenantContext, get_tenant_context
from app.entitlements import require_feature
from app.retrieval.service import answer_question

router = APIRouter(prefix="/v1", tags=["expert-chat"])


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


@router.post("/analyses/{analysis_id}/chat")
async def post_chat(
    analysis_id: str,
    body: ChatRequest,
    request: Request,
    _: None = Depends(require_feature("workbench.chat")),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> dict:
    # Per-user workbench: the thread hangs off the CALLER's own analysis.
    analysis = await ctx.db.fetchval(
        "SELECT id FROM document_analyses WHERE id = $1::uuid AND created_by = $2",
        uuid.UUID(analysis_id),
        ctx.user_ref,
    )
    if analysis is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="analysis not found")

    thread_id = await ctx.db.fetchval(
        "SELECT id FROM expert_chat_threads"
        " WHERE analysis_id = $1::uuid AND created_by = $2",
        uuid.UUID(analysis_id),
        ctx.user_ref,
    )
    if thread_id is None:
        thread_id = uuid.uuid4()
        await ctx.db.execute(
            "INSERT INTO expert_chat_threads (id, tenant_id, analysis_id, created_by)"
            " VALUES ($1, $2, $3, $4)",
            thread_id,
            uuid.UUID(ctx.tenant_id),
            uuid.UUID(analysis_id),
            ctx.user_ref,
        )

    settings = request.app.state.settings
    result = await answer_question(
        body.question,
        {},
        ctx.db,
        ctx.tenant_id,
        ctx.user_ref,
        settings=settings,
        thread_id=str(thread_id),
        analysis_id=analysis_id,
    )
    return {**result, "thread_id": str(thread_id)}


@router.get("/analyses/{analysis_id}/chat")
async def list_chat(
    analysis_id: str,
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> dict:
    thread_id = await ctx.db.fetchval(
        "SELECT id FROM expert_chat_threads"
        " WHERE analysis_id = $1::uuid AND created_by = $2",
        uuid.UUID(analysis_id),
        ctx.user_ref,
    )
    if thread_id is None:
        return {"thread_id": None, "turns": []}
    rows = await ctx.db.fetch(
        "SELECT question_hash, answer_text, citations, serving_provider,"
        " created_at FROM query_audit WHERE thread_id = $1::uuid"
        " ORDER BY created_at",
        thread_id,
    )
    turns = []
    for r in rows:
        citations = r["citations"]
        if isinstance(citations, str):
            citations = json.loads(citations)
        turns.append(
            {
                "question_hash": r["question_hash"],
                "answer_text": r["answer_text"],
                "citations": citations or [],
                "serving_provider": r["serving_provider"],
                "created_at": r["created_at"].isoformat(),
            }
        )
    return {"thread_id": str(thread_id), "turns": turns}
