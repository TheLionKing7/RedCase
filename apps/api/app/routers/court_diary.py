"""Tenant-scoped Court Diary API."""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.deps import TenantContext, get_tenant_context

router = APIRouter(prefix="/v1/court-diary", tags=["court-diary"])


class DiaryEntryCreate(BaseModel):
    matter_id: UUID
    source_document_id: UUID | None = None
    event_id: UUID | None = None
    title: str = Field(min_length=1, max_length=240)
    entry_type: str = Field(pattern="^(HEARING|FILING|MENTION|OTHER)$")
    starts_at: datetime
    ends_at: datetime | None = None
    courtroom: str | None = Field(default=None, max_length=160)
    judge: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=2000)


@router.get("/entries")
async def list_entries(ctx: TenantContext = Depends(get_tenant_context)) -> list[dict]:
    rows = await ctx.db.fetch(
        "SELECT id,matter_id,source_document_id,event_id,title,entry_type,starts_at,ends_at,"
        "courtroom,judge,notes,status,created_by,created_at FROM court_diary_entries "
        "WHERE tenant_id=$1 ORDER BY starts_at ASC",
        ctx.tenant_id,
    )
    return [dict(row) for row in rows]


@router.post("/entries", status_code=status.HTTP_201_CREATED)
async def create_entry(body: DiaryEntryCreate, ctx: TenantContext = Depends(get_tenant_context)) -> dict:
    if body.ends_at and body.ends_at < body.starts_at:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="ends_at must be after starts_at")
    matter = await ctx.db.fetchval(
        "SELECT id FROM matters WHERE id=$1 AND tenant_id=$2", body.matter_id, ctx.tenant_id
    )
    if matter is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="matter not found in this tenant")
    row = await ctx.db.fetchrow(
        "INSERT INTO court_diary_entries (tenant_id,matter_id,source_document_id,event_id,title,entry_type,"
        "starts_at,ends_at,courtroom,judge,notes,created_by) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12) "
        "RETURNING id,matter_id,source_document_id,event_id,title,entry_type,starts_at,ends_at,courtroom,judge,notes,status,created_by,created_at",
        ctx.tenant_id, body.matter_id, body.source_document_id, body.event_id, body.title, body.entry_type,
        body.starts_at, body.ends_at, body.courtroom, body.judge, body.notes, ctx.user_ref,
    )
    return dict(row)