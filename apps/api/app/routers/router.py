"""POST /v1/dual/query — Task 2.4 dual-vault router endpoint (Phase2 §2).

Gated by require_feature("core.dual_vault"): a CORE feature (never in
PREMIUM_FEATURES), so the gate always ALLOWs — but it still writes its
entitlement_events DECISION row, which is what "inert behind the existing
entitlement layer" means for a core surface: the metering exists from day
one and a plan change can promote the feature without a code path appearing.

matter_id is client-supplied (matter channel context per §2.2); the
matter-binding ruling (pre-filter unless PARTNER/ADMIN clearance) is
applied in router.service, not here.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.deps import TenantContext, get_tenant_context
from app.entitlements import require_feature
from app.middleware.zdr import get_logger
from app.router.service import Mode, dual_vault_query

log = get_logger("redcase.router.api")

router = APIRouter(prefix="/v1", tags=["dual-query"])


class DualQueryRequest(BaseModel):
    question: str
    matter_id: str | None = None
    mode: Mode = Mode.HYBRID


class DualQueryResponse(BaseModel):
    answer: str
    citations: list[dict[str, Any]]
    refusal: bool
    route: str
    advisory: bool = False


@router.post("/dual/query", response_model=DualQueryResponse)
async def run_dual_query(
    req: DualQueryRequest,
    request: Request,
    _: None = Depends(require_feature("core.dual_vault")),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> DualQueryResponse:
    settings = request.app.state.settings  # per-app instance, not the lru_cache
    try:
        result = await dual_vault_query(
            question=req.question,
            conn=ctx.db,
            tenant_id=ctx.tenant_id,
            user_ref=ctx.user_ref,
            clearance=ctx.clearance,
            settings=settings,
            matter_id=req.matter_id,
            mode=req.mode,
        )
    except RuntimeError as exc:
        # Unprovisioned model/key credentials — distinct from a refusal.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return DualQueryResponse(**result)
