"""Ingest-to-DB integration tests — Task 1.3 synthetic DoD.

Runs the real upsert path against the embedded Postgres (session fixture):
document row + page-pinned chunks + 3072-dim embeddings, RLS GUC enforcement,
and idempotent re-ingest. Corpus-dependent DoD items (10 benchmark PDFs,
spot-checks on real documents) stay deferred per owner instruction.
"""

import uuid

import asyncpg
import pytest
from conftest import SEED_TENANT_AETOES

from app.ingestion.chunker import chunk_pages
from app.ingestion.db import EMBEDDING_DIMS, ingest_pdf
from tests.pdf_factory import make_pdf, synthetic_judgment_pages

VAULT_JURIS_NG = uuid.UUID("b0000001-0000-4000-8000-000000000001")


class FakeEmbedder:
    """Deterministic 3072-dim embeddings — no network, no secrets."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[(len(t) % 97) / 97.0] * EMBEDDING_DIMS for t in texts]


@pytest.fixture
async def seeded_pdf(tmp_path):
    # Unique citation per test so the (tenant_id, citation_norm) unique
    # constraint never collides across tests sharing the session DB.
    n = int(uuid.uuid4().hex[:6], 16)
    year = 1990 + (n % 30)
    citation = f"({year}) {1 + n % 9} NWLR (Pt. {100 + n % 900}) {1 + n % 500}"
    pages = synthetic_judgment_pages()
    pages[0] = [citation if "NWLR CITATION" in line else line for line in pages[0]]
    return make_pdf(tmp_path / f"judgment-{n}.pdf", pages), citation, year


class TestIngestPdf:
    async def test_ingest_persists_document_and_chunks(
        self, app_db_url: str, seeded_pdf
    ) -> None:
        pdf_path, citation, year = seeded_pdf
        conn = await asyncpg.connect(app_db_url)
        try:
            result = await ingest_pdf(
                conn, tenant_id=uuid.UUID(SEED_TENANT_AETOES),
                vault_id=VAULT_JURIS_NG, pdf_path=pdf_path,
                embedder=FakeEmbedder(),
            )
            assert result.skipped is False
            assert result.chunks > 1

            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.tenant_id', $1, true)",
                    SEED_TENANT_AETOES,
                )
                doc = await conn.fetchrow(
                    "SELECT case_title, citation, court_level, year, justices,"
                    " metadata_confidence, pdf_sha256 FROM documents WHERE id = $1",
                    result.document_id,
                )
                assert doc["citation"] == citation
                assert doc["court_level"] == "SUPREME_COURT"
                assert doc["year"] == year
                assert "Musdapher, JSC" in doc["justices"]
                assert doc["metadata_confidence"] == 1.0
                assert len(doc["pdf_sha256"]) == 64

                rows = await conn.fetch(
                    "SELECT chunk_index, page_start, page_end, paragraph_refs,"
                    " is_ratio, embedding::text AS emb FROM document_chunks"
                    " WHERE document_id = $1 ORDER BY chunk_index",
                    result.document_id,
                )
                expected = chunk_pages_from_file(pdf_path)
                assert [r["chunk_index"] for r in rows] == [c.chunk_index for c in expected]
                for row, chunk in zip(rows, expected, strict=True):
                    assert row["page_start"] == chunk.page_start
                    assert row["page_end"] == chunk.page_end
                    assert [str(x) for x in row["paragraph_refs"]] == chunk.paragraph_refs
                    assert row["is_ratio"] == chunk.is_ratio
                    assert row["emb"].startswith("[") and len(row["emb"]) > 1000
        finally:
            await conn.close()

    async def test_reingest_is_noop(self, app_db_url: str, seeded_pdf) -> None:
        pdf_path, _citation, _year = seeded_pdf
        conn = await asyncpg.connect(app_db_url)
        try:
            first = await ingest_pdf(
                conn, tenant_id=uuid.UUID(SEED_TENANT_AETOES),
                vault_id=VAULT_JURIS_NG, pdf_path=pdf_path,
                embedder=FakeEmbedder(),
            )
            second = await ingest_pdf(
                conn, tenant_id=uuid.UUID(SEED_TENANT_AETOES),
                vault_id=VAULT_JURIS_NG, pdf_path=pdf_path,
                embedder=FakeEmbedder(),
            )
            assert first.skipped is False
            assert second.skipped is True
            assert second.document_id == first.document_id
            assert second.chunks == 0
        finally:
            await conn.close()

    async def test_rls_blocks_cross_tenant_read(
        self, app_db_url: str, seeded_pdf
    ) -> None:
        pdf_path, citation, year = seeded_pdf
        conn = await asyncpg.connect(app_db_url)
        try:
            result = await ingest_pdf(
                conn, tenant_id=uuid.UUID(SEED_TENANT_AETOES),
                vault_id=VAULT_JURIS_NG, pdf_path=pdf_path,
                embedder=FakeEmbedder(),
            )
            intruder = str(uuid.uuid4())
            await conn.execute(
                "INSERT INTO tenants (id, name, slug) VALUES ($1, 'Intruder', $2)",
                intruder, f"intr-{intruder[:8]}",
            )
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.tenant_id', $1, true)", intruder
                )
                assert await conn.fetchval(
                    "SELECT count(*) FROM documents WHERE id = $1",
                    result.document_id,
                ) == 0
        finally:
            await conn.close()

    async def test_no_embed_persists_null_vectors(
        self, app_db_url: str, seeded_pdf
    ) -> None:
        """Backfill-deferred path (owner-approved 2026-09-16): with no usable
        embedding credential, ingest_pdf(embedder=None) must still persist
        the document and page-pinned chunks, with embedding NULL so the hnsw
        index skips them until backfill."""
        pdf_path, _citation, _year = seeded_pdf
        conn = await asyncpg.connect(app_db_url)
        try:
            result = await ingest_pdf(
                conn, tenant_id=uuid.UUID(SEED_TENANT_AETOES),
                vault_id=VAULT_JURIS_NG, pdf_path=pdf_path, embedder=None,
            )
            assert result.skipped is False
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.tenant_id', $1, true)",
                    SEED_TENANT_AETOES,
                )
                rows = await conn.fetch(
                    "SELECT embedding FROM document_chunks WHERE document_id = $1",
                    result.document_id,
                )
                assert len(rows) == result.chunks
                assert all(r["embedding"] is None for r in rows)
        finally:
            await conn.close()


def chunk_pages_from_file(path):
    import pymupdf

    with pymupdf.open(path) as doc:
        return chunk_pages([p.get_text("text") for p in doc])
