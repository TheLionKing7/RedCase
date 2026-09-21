"""Transparency feed — a redacted, read-only view over the audit tables (Addendum §7.3).

Partners get a live transparency view that MATCHES query_audit (parity), but
only its metadata — question hashes, threshold/latency, serving provider,
timestamps. Never answer_text, citations, or question bodies (ZDR). RLS
tenant_isolation scopes the feed to the caller's tenant.

This is the read side of the append-only audit; the write side is immutable
(migration 0011 + conftest REVOKE + TestAuditImmutability).
"""

from fastapi import APIRouter, Depends

from app.deps import TenantContext, get_tenant_context

router = APIRouter(prefix="/v1", tags=["audit"])


@router.get("/audit")
async def list_audit(
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> dict:
    rows = await ctx.db.fetch(
        "SELECT question_hash, threshold_passed, latency_ms, serving_provider,"
        " serving_model, created_at"
        " FROM query_audit ORDER BY created_at DESC LIMIT 200"
    )
    return {
        "entries": [
            {
                "question_hash": r["question_hash"],
                "threshold_passed": r["threshold_passed"],
                "latency_ms": r["latency_ms"],
                "serving_provider": r["serving_provider"],
                "serving_model": r["serving_model"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]
    }
