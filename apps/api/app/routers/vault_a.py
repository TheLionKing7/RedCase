"""Vault A document endpoints — Task 2.3 (owner brief 2026-09-19).

  POST /v1/matters/{matter_id}/documents   — raw PDF body; classification,
                                             doc_type, title, grantees as
                                             query params. Auth: Supabase
                                             JWT (existing layer); write
                                             authorization is app-layer in
                                             app.vault_a.ingest (ruling 2a).
  GET  /v1/matters/{matter_id}/documents   — list caller-visible documents
                                             (RLS-filtered; no existence
                                             oracle for foreign matters).
  GET  /v1/documents/{document_id}         — metadata + DECRYPTED chunks
                                             (decrypt-on-retrieve, DoD 2c).

Body is raw ``application/pdf`` bytes rather than multipart: the pipeline
trusts the hash, not the filename, and it keeps the endpoint testable
without extra dependencies. Slack attachment intake (2.6) downloads the
bytes and calls the same pipeline — one ingestion path, one audit story.

ZDR: no document content in logs or errors (HANDOFF.md 2.1).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.deps import TenantContext, get_tenant_context
from app.middleware.zdr import get_logger
from app.retrieval.clients import make_embedder
from app.vault_a.crypto import make_key_provider
from app.vault_a.ingest import (
    IntakeError,
    _parse_grantees,
    intake_document,
    read_document_decrypted,
)

log = get_logger("redcase.vault_a")

router = APIRouter(tags=["vault-a"])


@router.get("/v1/vault/documents")
async def list_vault_documents(
    vault_type: str,
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008
) -> dict:
    """List visible Vault A or B metadata; SQL RLS is the access boundary."""
    if vault_type not in {"firm", "juris"}:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "vault_type must be firm or juris",
        )
    rows = await ctx.db.fetch(
        "SELECT d.id, d.case_title, d.citation, d.doc_type, d.classification_level,"
        " d.ingested_at, d.matter_id FROM documents d JOIN vaults v ON v.id = d.vault_id"
        " WHERE v.vault_type = $1 ORDER BY d.ingested_at DESC LIMIT 100",
        vault_type,
    )
    return {"documents": [
        {"document_id": str(r["id"]), "title": r["case_title"], "citation": r["citation"],
         "doc_type": r["doc_type"], "classification": r["classification_level"],
         "ingested_at": r["ingested_at"].isoformat() if r["ingested_at"] else None,
         "matter_id": str(r["matter_id"]) if r["matter_id"] else None}
        for r in rows
    ]}


@router.post("/v1/matters/{matter_id}/documents")
async def ingest_document(
    request: Request,
    matter_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008 (FastAPI idiom)
    classification: str | None = Query(default=None),
    doc_type: str | None = Query(default=None),
    title: str | None = Query(default=None),
    grantees: str | None = Query(default=None),
) -> dict:
    raw = await request.body()
    if not raw:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "empty body")
    settings = request.app.state.settings
    try:
        return await intake_document(
            conn=ctx.db,
            settings=settings,
            provider=make_key_provider(settings),
            embedder=make_embedder(settings),
            tenant_id=ctx.tenant_id,
            uploader=ctx.user_ref,
            uploader_clearance=ctx.clearance,
            matter_id=matter_id,
            raw=raw,
            filename=title or "upload.pdf",
            classification=classification,
            doc_type=doc_type,
            grantees=_parse_grantees(grantees),
        )
    except IntakeError as exc:
        # Ruling violations and malformed input are 4xx, never 5xx — and
        # the message carries no document content.
        raise HTTPException(exc.code, str(exc)) from exc


@router.get("/v1/matters/{matter_id}/documents")
async def list_documents(
    matter_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008 (FastAPI idiom)
) -> dict:
    rows = await ctx.db.fetch(
        "SELECT id, case_title, classification_level, doc_type, citation"
        " FROM documents WHERE matter_id = $1 ORDER BY ingested_at",
        matter_id,
    )
    return {
        "matter_id": str(matter_id),
        "documents": [
            {
                "document_id": str(r["id"]),
                "case_title": r["case_title"],
                "classification_level": r["classification_level"],
                "doc_type": r["doc_type"],
                "citation": r["citation"],
            }
            for r in rows
        ],
    }


@router.get("/v1/documents/{document_id}")
async def get_document(
    document_id: uuid.UUID,
    request: Request,
    ctx: TenantContext = Depends(get_tenant_context),  # noqa: B008 (FastAPI idiom)
) -> dict:
    settings = request.app.state.settings
    doc = await read_document_decrypted(
        conn=ctx.db,
        provider=make_key_provider(settings),
        document_id=document_id,
    )
    if doc is None:
        # RLS hides invisible rows — 404, not 403, so the endpoint is not
        # an existence oracle.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found")
    return doc
