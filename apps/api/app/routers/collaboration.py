"""Authenticated collaboration workspace contracts."""
from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from app.deps import TenantContext, get_tenant_context

router = APIRouter(prefix="/v1", tags=["collaboration"])

class PinCreate(BaseModel):
    resource_type: str = Field(pattern="^(CHANNEL|MESSAGE|THREAD|ANALYSIS|MATTER)$")
    resource_id: str
    label: str = Field(min_length=1, max_length=200)

@router.get("/pins")
async def list_pins(ctx: TenantContext = Depends(get_tenant_context)) -> list[dict]:
    rows = await ctx.db.fetch("SELECT id, resource_type, resource_id, label, created_at FROM user_pins ORDER BY created_at DESC")
    return [{"id": str(r["id"]), "resource_type": r["resource_type"], "resource_id": str(r["resource_id"]), "label": r["label"], "created_at": r["created_at"].isoformat()} for r in rows]

@router.post("/pins", status_code=201)
async def create_pin(body: PinCreate, ctx: TenantContext = Depends(get_tenant_context)) -> dict:
    try:
        resource_id = uuid.UUID(body.resource_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="resource_id must be a UUID") from exc
    # Validate references before inserting; this avoids cross-resource or cross-tenant pins.
    tables = {"CHANNEL": "channels", "MESSAGE": "channel_messages", "THREAD": "assistant_threads", "ANALYSIS": "document_analyses", "MATTER": "matters"}
    if await ctx.db.fetchval(f"SELECT id FROM {tables[body.resource_type]} WHERE id = $1", resource_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="resource not found")
    row = await ctx.db.fetchrow("""INSERT INTO user_pins (tenant_id, user_ref, resource_type, resource_id, label)
        VALUES ($1::uuid, $2, $3, $4, $5) ON CONFLICT (tenant_id, user_ref, resource_type, resource_id)
        DO UPDATE SET label = EXCLUDED.label RETURNING id, resource_type, resource_id, label, created_at""", uuid.UUID(ctx.tenant_id), ctx.user_ref, body.resource_type, resource_id, body.label)
    return {"id": str(row["id"]), "resource_type": row["resource_type"], "resource_id": str(row["resource_id"]), "label": row["label"], "created_at": row["created_at"].isoformat()}

@router.delete("/pins/{pin_id}", status_code=204)
async def delete_pin(pin_id: str, ctx: TenantContext = Depends(get_tenant_context)) -> None:
    try:
        parsed_id = uuid.UUID(pin_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="pin_id must be a UUID") from exc
    result = await ctx.db.execute("DELETE FROM user_pins WHERE id = $1", parsed_id)
    if result != "DELETE 1":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="pin not found")
