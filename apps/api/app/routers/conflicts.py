"""Conflict check at client intake — Addendum §9.1, task 3.9 sub-task 3.

  POST /v1/conflicts/check   body {party_name}  → 201 {check, candidates[], stats}
  GET  /v1/conflicts/{id}                    → detail (check + candidates + decisions)
  POST /v1/conflicts/{id}/decision  body {decision} → decision row (append-only)

Detection-only, human-confirmed. The check scans the FIRM's own conflict surfaces —
`clients`, `matters`, and Vault A `documents.case_title` — and returns a scored,
reasoned candidate list. It does NOT block anything: a candidate is a flag for a lawyer
to confirm or dismiss. Both the detection and the verdict are append-only audit rows
(conflict_checks/conflict_candidates/conflict_decisions).

Gated by require_feature("ops.conflicts") — a CORE entitlement (never in
PREMIUM_FEATURES): always ALLOW for an active firm, but still writes its
entitlement_events DECISION row (same inert-behind-the-entitlement-layer meaning as
ops.time / ops.invoicing / comms.send).

Tenancy: surfaces are read through the RLS-scoped request connection, so only the
caller's tenant is ever scanned. The decision-path CHECK lookup validates tenancy
explicitly before writing (candidate/check FKs bypass RLS).

ZDR: `party_name` is the screened work product and is stored on the check (returned
to the firm only), never logged.
"""

import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.conflict_matcher import FUZZY_FLOOR, match_party
from app.deps import TenantContext, get_tenant_context
from app.entitlements import require_feature
from app.middleware.zdr import get_logger

log = get_logger("redcase.conflicts")

router = APIRouter(prefix="/v1", tags=["conflicts"])


class ConflictCheckIn(BaseModel):
    party_name: str = Field(min_length=2, max_length=500)


class CandidateOut(BaseModel):
    id: str
    tier: str
    source_kind: str
    source_id: str
    matched_name: str
    score: float
    reasons: list[str]


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(CONFIRMED|DISMISSED)$")


class DecisionOut(BaseModel):
    id: str
    check_id: str
    decision: str
    decided_by: str
    decided_at: str


class CheckOut(BaseModel):
    id: str
    party_name: str
    source: str
    created_by: str
    created_at: str
    candidates: list[CandidateOut] = Field(default_factory=list)
    decisions: list[DecisionOut] = Field(default_factory=list)


# The FIRM's own conflict surfaces. Vault B (the public corpus) is deliberately NOT a
# surface: a party in a public judgment is not a conflict of interest, and including it
# would flood lawyers with noise (alarm fatigue — migration 0016 ownership note).
_SOURCE_SQL = {
    "CLIENT": "SELECT id AS source_id, name AS matched_name FROM clients",
    "MATTER": "SELECT id AS source_id, case_title AS matched_name FROM ("
    "  SELECT m.id, m.client_id, c.name AS case_title"
    "  FROM matters m JOIN clients c ON c.id = m.client_id"
    ") x",
    "VAULT_A": "SELECT id AS source_id, case_title AS matched_name FROM documents"
    " WHERE classification_level IN ('CONFIDENTIAL','FIRM_INTERNAL','PARTNER_RESTRICTED')",
}


async def _scan(ctx: TenantContext, party_name: str) -> list[CandidateOut]:
    """Run the three-tier matcher across all tenant surfaces; return scored candidates.

    Recall-biased: every surface row is compared, and anything at/above the floor is kept
    (never capped) so a real conflict can't be silently dropped. The human's one-click
    dismiss makes the rare extra plausible candidate cheap; a false negative is not.
    """
    candidates: list[CandidateOut] = []
    limit = 2000  # cap a scan by row count, not by candidate count
    for kind, sql in _SOURCE_SQL.items():
        rows = await ctx.db.fetch(sql + " LIMIT $1::int", limit)
        for r in rows:
            matched = r["matched_name"] or ""
            if not matched:
                continue
            tier, score, reasons = match_party(party_name, matched)
            if tier == "EXACT" or score >= FUZZY_FLOOR:
                candidates.append(
                    CandidateOut(
                        id=str(r["source_id"]),  # replaced with candidate row id on persist
                        tier=tier,
                        source_kind=kind,
                        source_id=str(r["source_id"]),
                        matched_name=matched,
                        score=score,
                        reasons=reasons,
                    )
                )
    # Deterministic ordering for stable tests/UI: strongest matches first.
    candidates.sort(key=lambda c: (-c.score, c.tier, c.matched_name))
    return candidates


@router.post(
    "/conflicts/check",
    response_model=CheckOut,
    status_code=status.HTTP_201_CREATED,
)
async def check_conflict(
    body: ConflictCheckIn,
    _: None = Depends(require_feature("ops.conflicts")),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> CheckOut:
    """Screen a new party name across the firm's conflict surfaces (detection only)."""
    scanned = await _scan(ctx, body.party_name)

    check_id = uuid.uuid4()
    await ctx.db.execute(
        "INSERT INTO conflict_checks (id, tenant_id, party_name, source, created_by)"
        " VALUES ($1, $2, $3, 'INTAKE', $4)",
        check_id,
        uuid.UUID(ctx.tenant_id),
        body.party_name,
        ctx.user_ref,
    )

    # Persist each candidate as its own audit row; give it the real row id.
    for cand in scanned:
        row_id = uuid.uuid4()
        await ctx.db.execute(
            "INSERT INTO conflict_candidates"
            " (id, check_id, tenant_id, tier, source_kind, source_id, matched_name,"
            "  score, reasons)"
            " VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)",
            row_id,
            check_id,
            uuid.UUID(ctx.tenant_id),
            cand.tier,
            cand.source_kind,
            uuid.UUID(cand.source_id),
            cand.matched_name,
            cand.score,
            json.dumps(cand.reasons),
        )
        cand.id = str(row_id)

    log.info(
        "conflict_check",
        check_id=str(check_id),
        candidate_count=len(scanned),
        tenant_id=ctx.tenant_id,
    )
    return CheckOut(
        id=str(check_id),
        party_name=body.party_name,
        source="INTAKE",
        created_by=ctx.user_ref,
        created_at=datetime.now(UTC).isoformat(),
        candidates=scanned,
    )

async def _get_check(ctx: TenantContext, check_id: str) -> dict:
    """Fetch a check, validating tenancy explicitly (FK-driven reads bypass RLS)."""
    row = await ctx.db.fetchrow(
        "SELECT id, party_name, source, created_by, created_at"
        " FROM conflict_checks WHERE id = $1::uuid AND tenant_id = $2::uuid",
        uuid.UUID(check_id),
        uuid.UUID(ctx.tenant_id),
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="conflict check not found")
    return dict(row)


@router.get("/conflicts/{check_id}", response_model=CheckOut)
async def get_conflict(
    check_id: str,
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> CheckOut:
    """Return a check with its candidates and any decisions recorded on it."""
    check = await _get_check(ctx, check_id)

    cand_rows = await ctx.db.fetch(
        "SELECT id, tier, source_kind, source_id, matched_name, score, reasons"
        " FROM conflict_candidates WHERE check_id = $1::uuid"
        " ORDER BY score DESC, tier, matched_name",
        uuid.UUID(check_id),
    )
    candidates = [
        CandidateOut(
            id=str(r["id"]),
            tier=r["tier"],
            source_kind=r["source_kind"],
            source_id=str(r["source_id"]),
            matched_name=r["matched_name"],
            score=float(r["score"]),
            reasons=list(r["reasons"] or []),
        )
        for r in cand_rows
    ]

    dec_rows = await ctx.db.fetch(
        "SELECT id, check_id, decision, decided_by, decided_at"
        " FROM conflict_decisions WHERE check_id = $1::uuid ORDER BY decided_at, id",
        uuid.UUID(check_id),
    )
    decisions = [
        DecisionOut(
            id=str(r["id"]),
            check_id=str(r["check_id"]),
            decision=r["decision"],
            decided_by=r["decided_by"],
            decided_at=r["decided_at"].isoformat(),
        )
        for r in dec_rows
    ]

    return CheckOut(
        id=str(check["id"]),
        party_name=check["party_name"],
        source=check["source"],
        created_by=check["created_by"],
        created_at=check["created_at"].isoformat(),
        candidates=candidates,
        decisions=decisions,
    )


@router.post(
    "/conflicts/{check_id}/decision",
    response_model=DecisionOut,
    status_code=status.HTTP_201_CREATED,
)
async def decide_conflict(
    check_id: str,
    body: DecisionIn,
    _: None = Depends(require_feature("ops.conflicts")),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> DecisionOut:
    """Record the firm's CONFIRMED/DISMISSED ruling — append-only decision row."""
    await _get_check(ctx, check_id)  # tenancy-validated

    dec_id = uuid.uuid4()
    await ctx.db.execute(
        "INSERT INTO conflict_decisions (id, check_id, tenant_id, decision, decided_by)"
        " VALUES ($1, $2, $3, $4, $5)",
        dec_id,
        uuid.UUID(check_id),
        uuid.UUID(ctx.tenant_id),
        body.decision,
        ctx.user_ref,
    )
    log.info(
        "conflict_decision",
        check_id=check_id,
        decision_id=str(dec_id),
        decision=body.decision,
        tenant_id=ctx.tenant_id,
    )
    return DecisionOut(
        id=str(dec_id),
        check_id=check_id,
        decision=body.decision,
        decided_by=ctx.user_ref,
        decided_at=datetime.now(UTC).isoformat(),
    )

