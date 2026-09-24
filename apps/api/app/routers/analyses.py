"""Legal Workbench analysis endpoints — Feature-Addendum §3.2, Steps A + C.

  POST /v1/documents/{id}/analyze   body {prompt_pack, matter_id?} → 202 {analysis_id}
  GET  /v1/analyses/{id}            → status + tabbed pack output

The worker runs the §2.1 four-agent chain through the §3.3 prompt-pack
registry (ADVERSAL_BRIEF / SUMMONS_RESPONSE / CONTRACT_REVIEW) as a FastAPI
background task on a pooled connection with the RLS GUC set inside its own
transaction. Audit integration (Step A req 4): exactly one query_audit row
per completed analysis, metadata only per ZDR — question_hash is a SHA-256
of the analysis descriptor (never document text), filters carry
{document_id, prompt_pack, status}, and analysis_id links the row. An
audit-write failure HALTs the worker and marks the analysis FAILED
(convention 3).
"""

import hashlib
import json
import time
import uuid
from typing import Any

import asyncpg
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    status,
)
from pydantic import BaseModel

from app.config import Settings
from app.deadline_detector import detect_deadlines
from app.deps import TenantContext, get_tenant_context
from app.entitlements import require_feature
from app.middleware.audit import write_audit
from app.middleware.zdr import get_logger
from app.redteam.engine import run_pack_analysis
from app.redteam.packs import PACKS

log = get_logger("redcase.analyses")

router = APIRouter(prefix="/v1", tags=["analyses"])

# §3.3 pack registry (Step C) — the endpoint validates prompt_pack against
# this; ADVERSAL_BRIEF is the Step A pack.
ALLOWED_PACKS = tuple(PACKS)


class AnalyzeRequest(BaseModel):
    prompt_pack: str
    matter_id: str | None = None


class AnalyzeAccepted(BaseModel):
    analysis_id: str


class AnalysisStatus(BaseModel):
    analysis_id: str
    document_id: str
    prompt_pack: str
    status: str
    output: dict[str, Any] | None = None
    confidence: dict[str, Any] | None = None
    error: str | None = None
    created_by: str
    created_at: str


async def _run_analysis_worker(
    settings: Settings,
    pool: asyncpg.Pool,
    analysis_id: str,
    document_id: str,
    tenant_id: str,
    user_ref: str,
    prompt_pack: str,
) -> None:
    """Background task: run the engine, persist output, write the audit row.
    Never raises into the response path (the client already got 202); any
    failure is recorded on the analysis row itself."""
    started = time.monotonic()
    try:
        pack = PACKS[prompt_pack]
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.tenant_id', $1, true)", tenant_id
                )
                output = await run_pack_analysis(
                    pack, document_id, tenant_id, conn, settings=settings
                )
                output_json = output.model_dump(by_alias=True, mode="json")
                await conn.execute(
                    "UPDATE document_analyses SET status = 'COMPLETE', output = $2::jsonb"
                    " WHERE id = $1",
                    uuid.UUID(analysis_id),
                    json.dumps(output_json),
                )
                await detect_deadlines(
                    conn,
                    tenant_id=tenant_id,
                    document_id=document_id,
                    text=json.dumps(output_json),
                )
                await write_audit(
                    conn,
                    {
                        "tenant_id": tenant_id,
                        "user_ref": user_ref,
                        "question_hash": hashlib.sha256(
                            f"analyze:{document_id}:{prompt_pack}".encode()
                        ).hexdigest(),
                        "filters": {
                            "document_id": document_id,
                            "prompt_pack": prompt_pack,
                            "status": "COMPLETE",
                        },
                        "threshold_passed": output.critic_verdict.pass_,
                        "analysis_id": analysis_id,
                        "latency_ms": int((time.monotonic() - started) * 1000),
                    },
                )
        log.info(
            "analysis_complete",
            analysis_id=analysis_id,
            document_id=document_id,
            prompt_pack=prompt_pack,
            critic_pass=output.critic_verdict.pass_,
        )
    except Exception as exc:  # noqa: BLE001 — worker must record, not explode
        log.warn("analysis_failed", analysis_id=analysis_id, error=str(exc))
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.tenant_id', $1, true)", tenant_id
                )
                await conn.execute(
                    "UPDATE document_analyses SET status = 'FAILED', error = $2"
                    " WHERE id = $1",
                    uuid.UUID(analysis_id),
                    str(exc)[:500],
                )
                try:
                    await write_audit(
                        conn,
                        {
                            "tenant_id": tenant_id,
                            "user_ref": user_ref,
                            "question_hash": hashlib.sha256(
                                f"analyze:{document_id}:{prompt_pack}".encode()
                            ).hexdigest(),
                            "filters": {
                                "document_id": document_id,
                                "prompt_pack": prompt_pack,
                                "status": "FAILED",
                            },
                            "threshold_passed": False,
                            "analysis_id": analysis_id,
                            "latency_ms": int((time.monotonic() - started) * 1000),
                        },
                    )
                except Exception:  # noqa: BLE001 — audit HALT already logged upstream
                    log.warn("analysis_audit_halt", analysis_id=analysis_id)


@router.post("/documents/{document_id}/analyze", status_code=202)
async def start_analysis(
    document_id: str,
    body: AnalyzeRequest,
    background: BackgroundTasks,
    request: Request,
    _: None = Depends(require_feature("workbench.analyze")),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> AnalyzeAccepted:
    if body.prompt_pack not in ALLOWED_PACKS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"prompt_pack must be one of {ALLOWED_PACKS} (Addendum"
            " 3.3 registry: ADVERSAL_BRIEF, SUMMONS_RESPONSE, CONTRACT_REVIEW)",
        )
    doc = await ctx.db.fetchval(
        "SELECT id FROM documents WHERE id = $1::uuid", document_id
    )
    if doc is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="document not found in this tenant's vault",
        )
    analysis_id = str(uuid.uuid4())
    # The analysis row must COMMIT before the 202 returns: the background
    # worker updates this row by id, and the dependency transaction that
    # owns ``ctx.db`` only commits after background tasks run — inserting
    # there would race the worker (its UPDATE would hit 0 rows, and the
    # audit row's FK would fail against the uncommitted analysis). A
    # dedicated short transaction keeps the contract: 202 means the
    # analysis exists and is RUNNING.
    async with request.app.state.db_pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.tenant_id', $1, true)", ctx.tenant_id
            )
            await conn.execute(
                "INSERT INTO document_analyses (id, tenant_id, document_id,"
                " matter_id, prompt_pack, created_by)"
                " VALUES ($1, $2, $3, $4, $5, $6)",
                uuid.UUID(analysis_id),
                uuid.UUID(ctx.tenant_id),
                uuid.UUID(document_id),
                uuid.UUID(body.matter_id) if body.matter_id else None,
                body.prompt_pack,
                ctx.user_ref,
            )
    settings: Settings = request.app.state.settings
    background.add_task(
        _run_analysis_worker,
        settings,
        request.app.state.db_pool,
        analysis_id,
        document_id,
        ctx.tenant_id,
        ctx.user_ref,
        body.prompt_pack,
    )
    log.info(
        "analysis_started",
        analysis_id=analysis_id,
        document_id=document_id,
        prompt_pack=body.prompt_pack,
    )
    return AnalyzeAccepted(analysis_id=analysis_id)


class ChainRequest(BaseModel):
    prompt_pack: str


@router.post("/analyses/{analysis_id}/chain", status_code=202)
async def chain_analysis(
    analysis_id: str,
    body: ChainRequest,
    background: BackgroundTasks,
    request: Request,
    _: None = Depends(require_feature("workbench.analyze")),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> AnalyzeAccepted:
    if body.prompt_pack not in ALLOWED_PACKS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"prompt_pack must be one of {ALLOWED_PACKS} — must differ from"
            " the source analysis's pack",
        )
    parent = await ctx.db.fetchrow(
        "SELECT id, tenant_id, document_id, prompt_pack FROM document_analyses"
        " WHERE id = $1::uuid",
        analysis_id,
    )
    if parent is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="analysis not found"
        )
    if parent["prompt_pack"] == body.prompt_pack:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Chained analysis must use a different prompt pack.",
        )
    child_id = str(uuid.uuid4())
    # Same contract as /analyze: the child row must COMMIT before the 202 returns
    # so the background worker (which updates by id) and the audit FK both resolve.
    async with request.app.state.db_pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.tenant_id', $1, true)", ctx.tenant_id
            )
            await conn.execute(
                "INSERT INTO document_analyses (id, tenant_id, document_id,"
                " prompt_pack, created_by, parent_analysis_id)"
                " VALUES ($1, $2, $3, $4, $5, $6)",
                uuid.UUID(child_id),
                parent["tenant_id"],
                parent["document_id"],
                body.prompt_pack,
                ctx.user_ref,
                uuid.UUID(analysis_id),
            )
    settings: Settings = request.app.state.settings
    background.add_task(
        _run_analysis_worker,
        settings,
        request.app.state.db_pool,
        child_id,
        str(parent["document_id"]),
        ctx.tenant_id,
        ctx.user_ref,
        body.prompt_pack,
    )
    log.info(
        "analysis_chained",
        parent_analysis_id=analysis_id,
        child_analysis_id=child_id,
        prompt_pack=body.prompt_pack,
    )
    return AnalyzeAccepted(analysis_id=child_id)


@router.get("/analyses", response_model=list[AnalysisStatus])
async def list_analyses(
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> list[AnalysisStatus]:
    """Per-user Workbench: the caller's own analyses (Addendum §6.2 'My
    Operations'). Scoped by the RLS session to this tenant and by created_by to
    this user. Newest first — the Workbench surfaces running/complete work."""

    def _json(v: Any) -> Any:
        return json.loads(v) if isinstance(v, str) else v

    rows = await ctx.db.fetch(
        "SELECT id, document_id, prompt_pack, status, output, confidence,"
        " error, created_by, created_at FROM document_analyses"
        " WHERE created_by = $1 ORDER BY created_at DESC LIMIT 100",
        ctx.user_ref,
    )
    return [
        AnalysisStatus(
            analysis_id=str(r["id"]),
            document_id=str(r["document_id"]),
            prompt_pack=r["prompt_pack"],
            status=r["status"],
            output=_json(r["output"]),
            confidence=_json(r["confidence"]),
            error=r["error"],
            created_by=r["created_by"],
            created_at=r["created_at"].isoformat(),
        )
        for r in rows
    ]


@router.get("/analyses/{analysis_id}", response_model=AnalysisStatus)
async def get_analysis(
    analysis_id: str,
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> AnalysisStatus:
    row = await ctx.db.fetchrow(
        "SELECT id, document_id, prompt_pack, status, output, confidence,"
        " error, created_by, created_at FROM document_analyses"
        " WHERE id = $1::uuid",
        analysis_id,
    )
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="analysis not found"
        )
    # asyncpg returns jsonb as str by default — decode for pydantic validation.
    output = row["output"]
    confidence = row["confidence"]
    if isinstance(output, str):
        output = json.loads(output)
    if isinstance(confidence, str):
        confidence = json.loads(confidence)
    return AnalysisStatus(
        analysis_id=str(row["id"]),
        document_id=str(row["document_id"]),
        prompt_pack=row["prompt_pack"],
        status=row["status"],
        output=output,
        confidence=confidence,
        error=row["error"],
        created_by=row["created_by"],
        created_at=row["created_at"].isoformat(),
    )
