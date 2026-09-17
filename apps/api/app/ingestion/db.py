"""Idempotent ingest-to-Postgres path (Task 1.3, Phase1-Design 4).

Contract:
  * RLS: every statement runs inside a transaction with ``app.tenant_id``
    SET LOCAL (HANDOFF.md 2.2; the 2.1 USING policy doubles as WITH CHECK
    on INSERT — inserts without the GUC are rejected).
  * Idempotency: dedup by ``pdf_sha256`` first, then by the
    ``(tenant_id, citation_norm)`` unique constraint; a re-ingest is a no-op
    that reports the existing document id.
  * ZDR: only metadata + chunks + embeddings persist (convention 1). No
    log line here may carry raw document text — ids and counts only.
"""

import asyncio
import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import asyncpg
import pymupdf

from app.ingestion.chunker import chunk_pages
from app.ingestion.metadata import extract_metadata
from app.middleware.zdr import get_logger

log = get_logger("redcase.ingest")

# Platform embedding size — the platform's canonical embedding model
# (nvidia/llama-nemotron-embed-vl-1b-v2 via OpenRouter) emits 2048 dims.
# CONFLICT RECORDED (HANDOFF.md rule 3, owner ruling 2026-09-17): Phase1-
# Design 2.1 mandates VECTOR(3072) for text-embedding-3-large; the only
# provisioned credential path serves 2048 dims, and migration 0006 moved
# the column to VECTOR(2048). Any provider configured for this platform
# must serve EMBEDDING_DIMS (ingest validates per batch).
EMBEDDING_DIMS = 2048


class Embedder(Protocol):
    """texts -> one vector per text. Production impl lives in scripts/ingest.py
    (OpenAI via the ZDR proxy); tests inject a deterministic fake."""

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class NullEmbedder:
    """Backfill-deferred ingest: rows land with embedding = NULL so the rest
    of the pipeline (chunks, page pins, metadata, RLS) is exercised live
    against the real corpus while no embedding credential is usable. The
    hnsw index skips NULLs, so retrieval stays correct on the pinned rows.
    Vectors MUST be backfilled before the VECTOR_GATE calibration runs."""

    async def embed(self, texts: list[str]) -> list[None]:
        return [None for _ in texts]


@dataclass(frozen=True)
class IngestResult:
    document_id: uuid.UUID
    citation: str
    chunks: int
    skipped: bool  # True when the document already existed (idempotent no-op)


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


async def ingest_pdf(
    conn: asyncpg.Connection,
    *,
    tenant_id: uuid.UUID,
    vault_id: uuid.UUID,
    pdf_path: Path,
    embedder: Embedder | None = None,
    source_pdf_path: str | None = None,
) -> IngestResult:
    raw = await asyncio.to_thread(Path(pdf_path).read_bytes)
    sha256 = hashlib.sha256(raw).hexdigest()

    async with conn.transaction():
        await conn.execute(
            "SELECT set_config('app.tenant_id', $1, true)", str(tenant_id)
        )
        existing = await conn.fetchval(
            "SELECT id FROM documents WHERE tenant_id = $1 AND pdf_sha256 = $2",
            tenant_id, sha256,
        )
        if existing:
            log.info("ingest_skipped", reason="sha256_exists", document_id=str(existing))
            row = await conn.fetchrow(
                "SELECT citation FROM documents WHERE id = $1", existing
            )
            return IngestResult(existing, row["citation"], 0, skipped=True)

        with pymupdf.open(stream=raw, filetype="pdf") as doc:
            pages_text = [p.get_text("text") for p in doc]
        meta = extract_metadata("\n".join(pages_text), Path(pdf_path).stem)
        chunks = chunk_pages(pages_text)

        if embedder is None:
            embeddings: list[list[float] | None] = [None] * len(chunks)
        else:
            embeddings = await embedder.embed([c.text for c in chunks])
            if len(embeddings) != len(chunks):
                raise RuntimeError("embedder returned a mismatched batch size")
            for vec in embeddings:
                if vec is not None and len(vec) != EMBEDDING_DIMS:
                    raise RuntimeError(
                        f"embedding has {len(vec)} dims; expected {EMBEDDING_DIMS}"
                    )

        document_id = uuid.uuid4()
        inserted = await conn.fetchval(
            """
            INSERT INTO documents
                (id, tenant_id, vault_id, case_title, citation, court_level,
                 year, justices, source_pdf_path, pdf_sha256,
                 metadata_confidence)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
            ON CONFLICT (tenant_id, citation_norm) DO NOTHING
            RETURNING id
            """,
            document_id, tenant_id, vault_id, meta.case_title, meta.citation,
            meta.court_level, meta.year, meta.justices,
            source_pdf_path or str(pdf_path), sha256, meta.metadata_confidence,
        )
        if inserted is None:
            existing = await conn.fetchval(
                "SELECT id FROM documents WHERE tenant_id = $1 AND citation_norm ="
                " upper(regexp_replace($2, '\\s+', ' ', 'g'))",
                tenant_id, meta.citation,
            )
            log.info("ingest_skipped", reason="citation_exists",
                     document_id=str(existing))
            return IngestResult(existing, meta.citation, 0, skipped=True)

        for chunk, vec in zip(chunks, embeddings, strict=True):
            await conn.execute(
                """
                INSERT INTO document_chunks
                    (id, tenant_id, document_id, chunk_index, chunk_text,
                     page_start, page_end, paragraph_refs, is_ratio, embedding)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::vector)
                """,
                uuid.uuid4(), tenant_id, document_id, chunk.chunk_index,
                chunk.text, chunk.page_start, chunk.page_end,
                chunk.paragraph_refs, chunk.is_ratio,
                _vec_literal(vec) if vec is not None else None,
            )

    log.info(
        "ingested",
        document_id=str(document_id),
        citation=meta.citation,
        chunks=len(chunks),
        confidence=meta.metadata_confidence,
    )
    return IngestResult(document_id, meta.citation, len(chunks), skipped=False)
