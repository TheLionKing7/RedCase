"""Personal attendance clock; intentionally separate from billable time entries."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.deps import TenantContext, get_tenant_context

router = APIRouter(prefix="/v1/activity-sessions", tags=["activity-sessions"])


class ClockInRequest(BaseModel):
    area: str = Field(default="General", min_length=1, max_length=160)


@router.get("")
async def list_sessions(ctx: TenantContext = Depends(get_tenant_context)) -> dict:  # noqa: B008
    rows = await ctx.db.fetch(
        "SELECT id, area, started_at, ended_at, duration FROM activity_sessions "
        "WHERE tenant_id=$1::uuid AND user_ref=$2 ORDER BY started_at DESC LIMIT 100",
        ctx.tenant_id, ctx.user_ref,
    )
    return {"sessions": [dict(row) for row in rows]}


@router.post("/clock-in", status_code=status.HTTP_201_CREATED)
async def clock_in(body: ClockInRequest, ctx: TenantContext = Depends(get_tenant_context)) -> dict:  # noqa: B008
    area = body.area.strip()
    if not area:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="area is required")
    row = await ctx.db.fetchrow(
        "INSERT INTO activity_sessions (tenant_id,user_ref,area) VALUES ($1::uuid,$2,$3) "
        "ON CONFLICT (tenant_id,user_ref) WHERE ended_at IS NULL DO NOTHING "
        "RETURNING id, area, started_at, ended_at, duration",
        ctx.tenant_id, ctx.user_ref, area,
    )
    if row is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="An activity session is already open.")
    return dict(row)


@router.post("/clock-out")
async def clock_out(ctx: TenantContext = Depends(get_tenant_context)) -> dict:  # noqa: B008
    row = await ctx.db.fetchrow(
        "UPDATE activity_sessions SET ended_at=now(), "
        "duration=GREATEST(0, floor(extract(epoch FROM (now()-started_at)))::integer) "
        "WHERE tenant_id=$1::uuid AND user_ref=$2 AND ended_at IS NULL "
        "RETURNING id, area, started_at, ended_at, duration",
        ctx.tenant_id, ctx.user_ref,
    )
    if row is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="No activity session is open.")
    return dict(row)