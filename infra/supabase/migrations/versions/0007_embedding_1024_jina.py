"""Embedding provider switch: nemotron/OpenRouter (2048) -> Jina v3 (1024).

CONFLICT RECORDED (HANDOFF.md rule 3, reported to owner): 0006 set the
platform embedding size to 2048 because the only provisioned credential
path was OpenRouter's free tier serving nvidia/llama-nemotron-embed-vl-1b-v2.
That path proved operationally unusable: the free tier caps at 20
embeds/min AND 50 free-model requests/day (verified 2026-09-18 — the
daily cap was exhausted mid-calibration by ~60 requests). Owner direction
same day: stop using the free tier; the only premium *embedding*
credential provisioned is JINA_API_KEY (DeepSeek serves chat models
only — no embeddings API). jina-embeddings-v3 outputs 1024 dims, so the
platform embedding size is now 1024; any provider configured for this
platform must serve 1024 dims (ingest validates EMBEDDING_DIMS per
batch). OpenRouter remains as a fallback credential path, but nemotron
:free must not be the platform default.

What this migration does, in order (same pattern as 0006):
  1. Clears every stored vector — 2048-dim nemotron vectors are
     meaningless after the model-family switch and must not be mixed
     with Jina vectors. scripts/backfill_embeddings.py re-embeds the
     corpus with the platform model.
  2. Alters the column to vector(1024) (all-NULL cast is trivial).
  3. Rebuilds the hnsw index over the halfvec(1024) cast (same minimal
     correction pattern as 0001/0006 — hnsw on plain vector caps at
     2000 dims; warn-skip where halfvec is unavailable).

Downgrade: dimension switches are lossy after backfill (1024 -> 2048
pads with zeros); the downgrade restores the type only — vectors must
be re-backfilled for the target model either way.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-18

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Clear stale vectors (see header): NULL embeddings refuse
    #    retrieval rather than mis-retrieve — the safe interim state.
    op.execute("UPDATE document_chunks SET embedding = NULL")
    # 2. Resize the column.
    op.execute(
        "ALTER TABLE document_chunks"
        " ALTER COLUMN embedding TYPE vector(1024)"
        " USING embedding::vector(1024)"
    )
    # 3. Rebuild the approximate index at the new dimension.
    op.execute("""
        DO $$
        BEGIN
            DROP INDEX IF EXISTS idx_chunks_embedding;
            CREATE INDEX idx_chunks_embedding ON document_chunks
                USING hnsw ((embedding::halfvec(1024)) halfvec_cosine_ops);
        EXCEPTION
            WHEN undefined_object OR feature_not_supported OR program_limit_exceeded THEN
                RAISE WARNING
                    'idx_chunks_embedding skipped (pgvector lacks halfvec(1024) '
                    'hnsw support here: %). Retrieval remains correct via the '
                    'exact <=> operator until the index can be built.',
                    SQLERRM;
        END $$
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_chunks_embedding")
    op.execute(
        "ALTER TABLE document_chunks"
        " ALTER COLUMN embedding TYPE vector(2048)"
        " USING embedding::vector(2048)"
    )
    op.execute("""
        DO $$
        BEGIN
            CREATE INDEX idx_chunks_embedding ON document_chunks
                USING hnsw ((embedding::halfvec(2048)) halfvec_cosine_ops);
        EXCEPTION
            WHEN undefined_object OR feature_not_supported OR program_limit_exceeded THEN
                RAISE WARNING 'idx_chunks_embedding skipped: %', SQLERRM;
        END $$
    """)
