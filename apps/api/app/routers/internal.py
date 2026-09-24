"""Internal maintenance endpoints (Task 1.7 deploy architecture).

POST /v1/internal/sweep — the Cloudflare Cron Trigger target (daily
07:00 Africa/Lagos). Authenticated by a shared internal token
(INTERNAL_SWEEP_TOKEN, SecretStr, constant-time compared); it is NOT a
user-facing route.

It runs platform maintenance for EVERY tenant, so unlike request-scoped
routes it cannot borrow a single JWT-derived app.tenant_id. Instead it
honours the same RLS contract as every other code path (HANDOFF.md 2.2:
SET LOCAL semantics per transaction via set_config(..., is_local=true)):
the tenants table carries no RLS policy, so the service role enumerates
tenants, then processes each tenant inside its own transaction with that
tenant's GUC placeholder set. A connection that never ran set_config()
would raise on the policy's current_setting('app.tenant_id') — the
fail-closed behaviour we want, worked around here the intended way, not
by bypassing RLS.

Current maintenance scope: backfill deferred-embedding chunks (Task 1.3
cleanup — chunks ingested with embedding NULL refuse retrieval). Same
logic as scripts/backfill_embeddings.py, kept self-contained so the
service and the CLI cannot drift apart silently; the script remains the
operator-facing variant.

ZDR: ids and counts only — no chunk text in logs (HANDOFF.md 2.1).
"""

import hmac
from datetime import date
from zoneinfo import ZoneInfo

import asyncpg
from fastapi import APIRouter, Header, HTTPException, Request, status

from app.config import Settings
from app.deadline_scheduler import sweep_deadline_notifications
from app.ingestion.db import _vec_literal
from app.middleware.zdr import get_logger
from app.retrieval.clients import make_embedder

log = get_logger("redcase.internal")

router = APIRouter(prefix="/v1/internal", tags=["internal"])

BATCH_SIZE = 32


def _require_internal_token(request: Request, x_internal_token: str | None) -> Settings:
    settings: Settings = request.app.state.settings
    expected = (
        settings.internal_sweep_token.get_secret_value()
        if settings.internal_sweep_token
        else None
    )
    # Unprovisioned endpoint fails CLOSED, and the comparison is constant-
    # time on both sides of the mismatch.
    if not expected or not x_internal_token or not hmac.compare_digest(
        expected.encode(), x_internal_token.encode()
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid internal token",
        )
    return settings


@router.post("/sweep")
async def sweep(
    request: Request,
    x_internal_token: str | None = Header(default=None),
) -> dict:
    """Run embedding maintenance and the deadline notification fan-out."""
    settings = _require_internal_token(request, x_internal_token)
    pool: asyncpg.Pool | None = request.app.state.db_pool
    if pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database not provisioned",
        )
    embedder = make_embedder(settings)

    # tenants has no RLS policy — the service role may enumerate them.
    async with pool.acquire() as conn:
        tenant_ids = [r["id"] for r in await conn.fetch("SELECT id FROM tenants")]

    pending = 0
    embedded = 0
    for tenant_id in tenant_ids:
        # Read this tenant's deferred chunks under its RLS scope. The
        # transaction is committed before embedding (network-bound work
        # must not hold DB transactions open); the UPDATE pass re-opens
        # a scoped transaction per batch.
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.fetchval(
                    "SELECT set_config('app.tenant_id', $1, true)", str(tenant_id)
                )
                rows = await conn.fetch(
                    "SELECT id, chunk_text FROM document_chunks"
                    " WHERE embedding IS NULL AND tenant_id = $1"
                    " ORDER BY document_id, chunk_index",
                    tenant_id,
                )
        if not rows:
            continue
        pending += len(rows)
        log.info("sweep_tenant_start", tenant_id=str(tenant_id), pending=len(rows))

        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i : i + BATCH_SIZE]
            vectors = await embedder.embed([r["chunk_text"] for r in batch])
            if len(vectors) != len(batch):
                raise RuntimeError("embedder returned a mismatched batch size")
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await conn.fetchval(
                        "SELECT set_config('app.tenant_id', $1, true)",
                        str(tenant_id),
                    )
                    for row, vec in zip(batch, vectors, strict=True):
                        await conn.execute(
                            "UPDATE document_chunks SET embedding = $2::vector"
                            " WHERE id = $1 AND tenant_id = $3",
                            row["id"],
                            _vec_literal(vec),
                            tenant_id,
                        )
            embedded += len(batch)
            log.info(
                "sweep_progress",
                tenant_id=str(tenant_id),
                embedded=embedded,
                total=pending,
            )

    notified = await _sweep_deadlines(pool)
    log.info("sweep_done", pending=pending, embedded=embedded, notified=notified)
    return {"pending": pending, "embedded": embedded, "deadline_notifications": notified}


async def _sweep_deadlines(pool: asyncpg.Pool) -> int:
    today = date.today()
    total = 0
    async with pool.acquire() as conn:
        tenant_ids = [r["id"] for r in await conn.fetch("SELECT id FROM tenants")]
    for tenant_id in tenant_ids:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.fetchval("SELECT set_config('app.tenant_id', $1, true)", str(tenant_id))
                total += await sweep_deadline_notifications(conn, tenant_id=str(tenant_id), today=today)
    return total
