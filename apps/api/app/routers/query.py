"""POST /v1/query — Phase1-Design §3.5 (Task 1.4)."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import Settings, get_settings
from app.deps import TenantContext, get_tenant_context
from app.retrieval.service import answer_question
from app.schemas import QueryRequest, QueryResponse

router = APIRouter(prefix="/v1", tags=["query"])


@router.post("/query", response_model=QueryResponse)
async def run_query(
    req: QueryRequest,
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> QueryResponse:
    try:
        result = await answer_question(
            req.question,
            req.model_dump(exclude={"question"}),
            ctx.db,
            ctx.tenant_id,
            ctx.user_ref,
            settings=settings,
        )
    except RuntimeError as exc:
        # Unprovisioned model credentials (embedder/LLM) — distinct from a
        # refusal: the caller must fix config, not rephrase the question.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return QueryResponse(**result)
