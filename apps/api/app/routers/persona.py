"""Agent persona + practice-area endpoints — Addendum §10.3 (S10-2).

  GET  /v1/persona              the caller's OWN persona (RLS tenant + owner isolation)
  PUT  /v1/persona              create-or-update the caller's persona (one per lawyer)
  GET  /v1/persona/practice-areas   the firm's practice-area defaults (read for onboarding)
  PUT  /v1/persona/practice-areas   upsert firm practice-area defaults (firm-admin gate)

Persona is per-user agent-level metadata (agent_name, rules_of_engagement, tone_preset,
practice_areas). It is injected into the assistant's ReAct system prompt AFTER the
GROUNDED_SYSTEM contract and BEFORE retrieval context (assistant/service.py). It shapes HOW the
assistant writes — it can never change WHAT it may cite (grounding survives byte-for-byte;
locked by tests). No model training (ZDR): style/preference metadata only, never document text
or LLM payloads.

RLS: agent_personas is scoped tenant + owner (a lawyer sees and edits ONLY their own row —
cross-user isolation, DoD 3). tenant_practice_areas is tenant-scoped; the write path is
firm-admin gated at the router (same pattern as KYC/admin surfaces).
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.assistant.service import PERSONA_TONES
from app.deps import TenantContext, get_tenant_context, require_firm_admin
from app.middleware.zdr import get_logger

log = get_logger("redcase.persona")

router = APIRouter(prefix="/v1/persona", tags=["persona"])


class PersonaUpsert(BaseModel):
    agent_name: str = Field(default="Assistant", max_length=120)
    rules_of_engagement: str | None = Field(default=None, max_length=4000)
    tone_preset: str = Field(default="PROFESSIONAL")
    practice_areas: list[str] = Field(default_factory=list, max_length=40)
    personality: str | None = Field(default=None, max_length=2000)
    working_style: str | None = Field(default=None, max_length=2000)
    reviewer_specialty: str | None = Field(default=None, max_length=2000)
    researcher_specialty: str | None = Field(default=None, max_length=2000)
    redteam_temperature: float = Field(default=0.2, ge=0.0, le=1.0)


class PracticeAreasUpsert(BaseModel):
    tags: list[str] = Field(min_length=1, max_length=40)


class DepartmentsUpsert(BaseModel):
    departments: list[str] = Field(min_length=1, max_length=10)


async def _persona_row(ctx: TenantContext):
    return await ctx.db.fetchrow(
        "SELECT agent_name, rules_of_engagement, tone_preset, practice_areas, personality,"
        " working_style, reviewer_specialty, researcher_specialty, redteam_temperature"
        " FROM agent_personas WHERE tenant_id = $1::uuid AND owner_ref = $2",
        uuid.UUID(ctx.tenant_id),
        ctx.user_ref,
    )


def _persona_payload(row) -> dict[str, Any]:
    return {
        "agent_name": row["agent_name"] or "Assistant",
        "rules_of_engagement": row["rules_of_engagement"],
        "tone_preset": row["tone_preset"] or "PROFESSIONAL",
        "practice_areas": list(row["practice_areas"] or []),
        "personality": row["personality"],
        "working_style": row["working_style"],
        "reviewer_specialty": row["reviewer_specialty"],
        "researcher_specialty": row["researcher_specialty"],
        "redteam_temperature": float(row["redteam_temperature"] or 0.2),
    }


@router.get("")
async def get_persona(
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> dict[str, Any]:
    """The caller's own persona (RLS isolates: only their row, only their tenant)."""
    row = await _persona_row(ctx)
    if row is None:
        return _persona_payload(
            {"agent_name": "Assistant", "rules_of_engagement": None,
             "tone_preset": "PROFESSIONAL", "practice_areas": [], "personality": None,
             "working_style": None, "reviewer_specialty": None, "researcher_specialty": None,
             "redteam_temperature": 0.2}
        )
    return _persona_payload(row)


@router.put("")
async def upsert_persona(
    body: PersonaUpsert,
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> dict[str, Any]:
    """Create-or-update the caller's OWN persona (UNIQUE tenant_id, owner_ref)."""
    if body.tone_preset not in PERSONA_TONES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"tone_preset must be one of {', '.join(PERSONA_TONES)}",
        )
    row = await ctx.db.fetchrow(
        "INSERT INTO agent_personas"
        " (tenant_id, owner_ref, agent_name, rules_of_engagement, tone_preset, practice_areas,"
        " personality, working_style, reviewer_specialty, researcher_specialty,"
        " redteam_temperature)"
        " VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)"
        " ON CONFLICT (tenant_id, owner_ref) DO UPDATE SET"
        "  agent_name = EXCLUDED.agent_name,"
        "  rules_of_engagement = EXCLUDED.rules_of_engagement,"
        "  tone_preset = EXCLUDED.tone_preset,"
        "  practice_areas = EXCLUDED.practice_areas,"
        "  personality = EXCLUDED.personality,"
        "  working_style = EXCLUDED.working_style,"
        "  reviewer_specialty = EXCLUDED.reviewer_specialty,"
        "  researcher_specialty = EXCLUDED.researcher_specialty,"
        "  redteam_temperature = EXCLUDED.redteam_temperature,"
        "  updated_at = now()"
        " RETURNING agent_name, rules_of_engagement, tone_preset, practice_areas, personality,"
        " working_style, reviewer_specialty, researcher_specialty, redteam_temperature",
        uuid.UUID(ctx.tenant_id),
        ctx.user_ref,
        body.agent_name[:120],
        body.rules_of_engagement,
        body.tone_preset,
        list(body.practice_areas) or None,
        body.personality,
        body.working_style,
        body.reviewer_specialty,
        body.researcher_specialty,
        body.redteam_temperature,
    )
    log.info("persona_upserted", tenant_id=ctx.tenant_id, user_ref=ctx.user_ref)
    return _persona_payload(row)


@router.get("/practice-areas")
async def get_practice_areas(
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> dict[str, Any]:
    """Firm-wide practice-area defaults (read for onboarding / workbench population)."""
    rows = await ctx.db.fetch(
        "SELECT tag FROM tenant_practice_areas WHERE tenant_id = $1::uuid ORDER BY tag",
        uuid.UUID(ctx.tenant_id),
    )
    return {"tags": [r["tag"] for r in rows]}


@router.put("/practice-areas")
async def upsert_practice_areas(
    body: PracticeAreasUpsert,
    ctx: TenantContext = Depends(require_firm_admin),  # noqa: B008
) -> dict[str, Any]:
    """Firm practice-area defaults (firm-admin only). Replaces the full set."""
    await ctx.db.execute(
        "DELETE FROM tenant_practice_areas WHERE tenant_id = $1::uuid",
        uuid.UUID(ctx.tenant_id),
    )
    for tag in dict.fromkeys(t.strip() for t in body.tags if t.strip()):
        await ctx.db.execute(
            "INSERT INTO tenant_practice_areas (tenant_id, tag) VALUES ($1, $2)",
            uuid.UUID(ctx.tenant_id),
            tag[:120],
        )
    tags = list(dict.fromkeys(t.strip() for t in body.tags if t.strip()))
    log.info("practice_areas_upserted", tenant_id=ctx.tenant_id)
    return {"tags": sorted(tags)}


@router.get("/departments")
async def get_departments(
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> dict[str, Any]:
    rows = await ctx.db.fetch(
        "SELECT department FROM tenant_departments WHERE tenant_id = $1::uuid ORDER BY department",
        uuid.UUID(ctx.tenant_id),
    )
    return {"departments": [r["department"] for r in rows]}


@router.put("/departments")
async def upsert_departments(
    body: DepartmentsUpsert,
    ctx: TenantContext = Depends(require_firm_admin),  # noqa: B008
) -> dict[str, Any]:
    """Firm department modules (firm-admin only). Legal Practice is mandatory."""
    departments = list(dict.fromkeys(d.strip() for d in body.departments if d.strip()))
    if "Legal Practice" not in departments:
        departments.insert(0, "Legal Practice")
    await ctx.db.execute(
        "DELETE FROM tenant_departments WHERE tenant_id = $1::uuid",
        uuid.UUID(ctx.tenant_id),
    )
    for department in departments:
        await ctx.db.execute(
            "INSERT INTO tenant_departments (tenant_id, department) VALUES ($1, $2)",
            uuid.UUID(ctx.tenant_id),
            department[:120],
        )
    log.info("departments_upserted", tenant_id=ctx.tenant_id)
    return {"departments": sorted(departments)}
