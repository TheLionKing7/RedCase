"""Embedding dimension switch: VECTOR(3072) -> VECTOR(2048) (owner ruling
2026-09-17).

CONFLICT RECORDED (HANDOFF.md rule 3, reported to owner): Phase1-Design
2.1 mandates VECTOR(3072) (text-embedding-3-large). The only provisioned
embedding credential path is OpenRouter serving
nvidia/llama-nemotron-embed-vl-1b-v2 at 2048 dims (verified live
2026-09-17; the NVIDIA NIM endpoint 404s for that model id — it is an
OpenRouter identifier). The platform embedding size is therefore 2048;
any provider configured for this platform must serve 2048 dims (ingest
validates EMBEDDING_DIMS per batch).

What this migration does, in order:
  1. Clears every stored vector. Chunks ingested under the deferred-embed
     path (Task 1.3, --no-embed) have NULL already; any 3072-dim vector
     from a different model family is meaningless after the switch and
     must not be mixed with nemotron vectors. scripts/backfill_embeddings.py
     re-embeds the corpus with the platform model.
  2. Alters the column to vector(2048). pgvector >= 0.5 supports casting
     between dimensions (the USING cast would truncate); with step 1 the
     column is all-NULL so the cast is trivial.
  3. Rebuilds the hnsw index over the halfvec(2048) cast — same minimal
     correction pattern as 0001 (hnsw on plain vector caps at 2000 dims),
     now at the new dimension. Warn-skips where halfvec is unavailable
     (embedded test Postgres bundles pgvector 0.6.2 — which does support
     halfvec since 0.7... see 0001: the index may warn-skip there; NULL
     columns make the index optional until backfill).

Downgrade: dimension switches are lossy after backfill (2048 -> 3072 pads
with zeros); the downgrade restores the type only — vectors must be
re-backfilled for the target model either way.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-17

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Clear stale vectors (see header): NULL embeddings refuse
    #    retrieval rather than mis-retrieve — the safe interim state.
    op.execute("UPDATE document_chunks SET embedding = NULL")
    # 2. Resize the column.
    op.execute(
        "ALTER TABLE document_chunks"
        " ALTER COLUMN embedding TYPE vector(2048)"
        " USING embedding::vector(2048)"
    )
    # 3. Rebuild the approximate index at the new dimension.
    op.execute("""
        DO $$
        BEGIN
            DROP INDEX IF EXISTS idx_chunks_embedding;
            CREATE INDEX idx_chunks_embedding ON document_chunks
                USING hnsw ((embedding::halfvec(2048)) halfvec_cosine_ops);
        EXCEPTION
            WHEN undefined_object OR feature_not_supported OR program_limit_exceeded THEN
                RAISE WARNING
                    'idx_chunks_embedding skipped (pgvector lacks halfvec(2048) '
                    'hnsw support here: %). Retrieval remains correct via the '
                    'exact <=> operator until the index can be built.',
                    SQLERRM;
        END $$
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_chunks_embedding")
    op.execute(
        "ALTER TABLE document_chunks"
        " ALTER COLUMN embedding TYPE vector(3072)"
        " USING embedding::vector(3072)"
    )
    op.execute("""
        DO $$
        BEGIN
            CREATE INDEX idx_chunks_embedding ON document_chunks
                USING hnsw ((embedding::halfvec(3072)) halfvec_cosine_ops);
        EXCEPTION
            WHEN undefined_object OR feature_not_supported OR program_limit_exceeded THEN
                RAISE WARNING 'idx_chunks_embedding skipped: %', SQLERRM;
        END $$
    """)
