"""Personal attendance clock; intentionally separate from billable time entries."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from app.deps import TenantContext, get_tenant_context

router = APIRouter(prefix="/v1/activity-sessions", tags=["activity-sessions"])


class ClockInRequest(BaseModel):
    area: str = Field(default="General", min_length=1, max_length=160)
    target_type: str | None = Field(default=None, pattern="^(matter|area)$")
    target_ref: str | None = Field(default=None, min_length=1, max_length=256)

    @model_validator(mode="after")
    def require_target_pair(self) -> "ClockInRequest":
        if (self.target_type is None) != (self.target_ref is None):
            raise ValueError("target_type and target_ref must be provided together")
        return self

@router.get("")
async def list_sessions(ctx: TenantContext = Depends(get_tenant_context)) -> dict:  # noqa: B008
    rows = await ctx.db.fetch(
        "SELECT s.id, s.area, s.target_type, s.target_ref, "
        "CASE WHEN s.target_type = 'matter' THEN m.matter_ref ELSE s.target_ref END AS target_label, "
        "s.started_at, s.ended_at, s.duration FROM activity_sessions s "
        "LEFT JOIN matters m ON s.target_type = 'matter' AND m.id::text = s.target_ref "
        "AND m.tenant_id = s.tenant_id "
        "WHERE s.tenant_id=$1::uuid AND s.user_ref=$2 ORDER BY s.started_at DESC LIMIT 100",
        ctx.tenant_id, ctx.user_ref,
    )
    groups = await ctx.db.fetch(
        "SELECT COALESCE(s.target_type, 'area') AS target_type, "
        "COALESCE(s.target_ref, s.area) AS target_ref, "
        "CASE WHEN s.target_type = 'matter' THEN m.matter_ref "
        "ELSE COALESCE(s.target_ref, s.area) END AS target_label, "
        "SUM(COALESCE(s.duration, "
        "floor(extract(epoch FROM (now()-s.started_at)))::integer))::bigint "
        "AS total_duration, COUNT(*)::integer AS session_count "
        "FROM activity_sessions s "
        "LEFT JOIN matters m ON s.target_type = 'matter' AND m.id::text = s.target_ref "
        "AND m.tenant_id = s.tenant_id "
        "WHERE s.tenant_id=$1::uuid AND s.user_ref=$2 "
        "GROUP BY COALESCE(s.target_type, 'area'), COALESCE(s.target_ref, s.area), "
        "CASE WHEN s.target_type = 'matter' THEN m.matter_ref "
        "ELSE COALESCE(s.target_ref, s.area) END "
        "ORDER BY MAX(s.started_at) DESC",
        ctx.tenant_id, ctx.user_ref,
    )
    return {
        "sessions": [dict(row) for row in rows],
        "groups": [dict(row) for row in groups],
    }


@router.post("/clock-in", status_code=status.HTTP_200_OK)
async def clock_in(body: ClockInRequest, ctx: TenantContext = Depends(get_tenant_context)) -> dict:  # noqa: B008
    area = body.area.strip()
    if not area:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="area is required")
    if (body.target_type is None) != (body.target_ref is None):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="target_type and target_ref must be provided together")
    if body.target_type == "matter":
        allowed = await ctx.db.fetchval(
            "SELECT 1 FROM matters WHERE id::text=$1 AND tenant_id=$2::uuid "
            "AND assigned_to=$3 LIMIT 1",
            body.target_ref, ctx.tenant_id, ctx.user_ref,
        )
        if not allowed:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="matter not found")
    elif body.target_type == "area" and body.target_ref not in {"Research", "Workbench", "General"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unsupported activity area")
    row = await ctx.db.fetchrow(
        "INSERT INTO activity_sessions (tenant_id,user_ref,area,target_type,target_ref) "
        "VALUES ($1::uuid,$2,$3,$4,$5) "
        "ON CONFLICT (tenant_id,user_ref) WHERE ended_at IS NULL DO NOTHING "
        "RETURNING id, area, target_type, target_ref, started_at, ended_at, duration",
        ctx.tenant_id, ctx.user_ref, area, body.target_type, body.target_ref,
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
        "RETURNING id, area, target_type, target_ref, started_at, ended_at, duration",
        ctx.tenant_id, ctx.user_ref,
    )
    if row is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="No activity session is open.")
    return dict(row)