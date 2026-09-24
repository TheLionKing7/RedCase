"""Validated deadline event API for the Statutory Tracker."""
from fastapi import APIRouter, Depends

from app.deps import TenantContext, get_tenant_context

router = APIRouter(prefix="/v1/deadlines", tags=["deadlines"])


@router.get("/events")
async def list_events(ctx: TenantContext = Depends(get_tenant_context)) -> list[dict]:
    rows = await ctx.db.fetch(
        "SELECT e.id,e.tenant_id,e.matter_id,e.source_document_id,e.rule_id,"
        "e.event_type,e.description,e.trigger_date,e.due_date,e.confidence,e.status,e.created_at,"
        "r.validated_by,r.validated_at,r.source_ref FROM deadline_events e "
        "JOIN deadline_rules r ON r.id=e.rule_id WHERE e.tenant_id=$1 ORDER BY e.due_date NULLS LAST",
        ctx.tenant_id,
    )
    return [dict(row) for row in rows]