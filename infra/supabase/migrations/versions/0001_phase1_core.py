"""Phase 1 core schema — Phase1-Design 2.1 DDL verbatim + tenant seed.

DDL below is transcribed from docs/RedCase-Phase1-Design.md 2.1 (source of
truth). Additions beyond the doc, recorded per HANDOFF.md rule 3:
  * ``CREATE EXTENSION IF NOT EXISTS vector`` — required for the vector types;
    available on Supabase by default.
  * DESIGN DOC BUG (reported to owner): 2.1's hnsw index on ``VECTOR(3072)``
    with ``vector_cosine_ops`` is impossible — pgvector caps hnsw/ivfflat on
    ``vector`` at 2000 dims in every released version, Supabase included.
    Minimal correction: keep ``VECTOR(3072)`` storage verbatim; build the
    hnsw index over the ``halfvec`` cast (supported to 4000 dims on
    pgvector >= 0.7; <=0.3 recall-point cost). Everything else matches 2.1
    verbatim.
  * Seed rows for tenant ``aetoes`` and its shared juris vault — Task 1.2 DoD
    ("seed tenant aetoes"). Fixed UUIDs keep tests and ingestion deterministic.

RLS note: policies use ``current_setting('app.tenant_id')`` with no default, so
any query without the GUC set fails closed (HANDOFF.md 2.2).

Revision ID: 0001
Revises:
Create Date: 2026-09-16

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Fixed seed UUIDs (deterministic for tests + Task 1.3 ingestion).
TENANT_AETOES = "a0000001-0000-4000-8000-000000000001"
VAULT_JURIS_NG = "b0000001-0000-4000-8000-000000000001"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # --- Tenancy scaffolding (multi-tenant from day one) ---
    op.execute("""
        CREATE TABLE tenants (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name        TEXT NOT NULL,
            slug        TEXT UNIQUE NOT NULL,
            jurisdiction TEXT NOT NULL DEFAULT 'NG',
            created_at  TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE vaults (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID NOT NULL REFERENCES tenants(id),
            vault_type  TEXT NOT NULL CHECK (vault_type IN ('firm', 'juris')),
            name        TEXT NOT NULL,
            is_shared   BOOLEAN DEFAULT FALSE,
            created_at  TIMESTAMPTZ DEFAULT now()
        )
    """)

    # --- Source documents (judgments, statutes) ---
    op.execute("""
        CREATE TABLE documents (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id    UUID NOT NULL REFERENCES tenants(id),
            vault_id     UUID NOT NULL REFERENCES vaults(id),
            case_title   TEXT NOT NULL,
            citation     TEXT NOT NULL,
            citation_norm TEXT GENERATED ALWAYS AS (upper(regexp_replace(citation, '\\s+', ' ', 'g'))) STORED,
            court_level  TEXT NOT NULL CHECK (court_level IN
                         ('SUPREME_COURT','COURT_OF_APPEAL','FEDERAL_HIGH_COURT',
                          'STATE_HIGH_COURT','NICN','STATUTE')),
            year         INT NOT NULL,
            justices     TEXT[],
            ratio_decidendi TEXT[],
            legal_topics TEXT[],
            source_pdf_path TEXT NOT NULL,
            pdf_sha256   TEXT NOT NULL,
            metadata_confidence NUMERIC(3,2),
            ingested_at  TIMESTAMPTZ DEFAULT now(),
            UNIQUE (tenant_id, citation_norm)
        )
    """)
    op.execute("""
        CREATE INDEX idx_documents_meta ON documents
            USING btree (tenant_id, court_level, year)
    """)
    op.execute("""
        CREATE INDEX idx_documents_ratio ON documents USING gin (ratio_decidendi)
    """)
    op.execute("""
        CREATE INDEX idx_documents_topics ON documents USING gin (legal_topics)
    """)

    # --- Chunks with page/paragraph pinning — the citation backbone ---
    op.execute("""
        CREATE TABLE document_chunks (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id    UUID NOT NULL REFERENCES tenants(id),
            document_id  UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            chunk_index  INT NOT NULL,
            chunk_text   TEXT NOT NULL,
            page_start   INT NOT NULL,
            page_end     INT NOT NULL,
            paragraph_refs TEXT[],
            is_ratio     BOOLEAN DEFAULT FALSE,
            embedding    VECTOR(3072),
            fts          TSVECTOR GENERATED ALWAYS AS
                         (to_tsvector('english', chunk_text)) STORED,
            UNIQUE (document_id, chunk_index)
        )
    """)
    # CONFLICT RECORDED (HANDOFF.md rule 3) — DESIGN DOC BUG, reported to
    # owner: 2.1 mandates hnsw (embedding vector_cosine_ops), but pgvector
    # caps hnsw/ivfflat on `vector` at 2000 dimensions in EVERY released
    # version (unchanged since 0.4.0, verified through 0.8.x) — so the 2.1
    # index cannot exist on Supabase either. Minimal correction preserving
    # the doc's column type verbatim: same VECTOR(3072) storage, with the
    # hnsw index built over the halfvec cast (pgvector >= 0.7, i.e. Supabase;
    # hnsw supports halfvec up to 4000 dims at <=0.3 recall-point cost).
    # Retrieval ORDER BY must mirror the cast (noted for Task 1.4). The
    # index warn-skips where halfvec is unavailable (embedded test Postgres
    # bundles pgvector 0.6.2).
    op.execute("""
        DO $$
        BEGIN
            CREATE INDEX idx_chunks_embedding ON document_chunks
                USING hnsw ((embedding::halfvec(3072)) halfvec_cosine_ops);
        EXCEPTION
            WHEN undefined_object OR feature_not_supported OR program_limit_exceeded THEN
                RAISE WARNING
                    'idx_chunks_embedding skipped (pgvector lacks halfvec(3072) '
                    'hnsw support here: %). Supabase (pgvector >= 0.7) creates '
                    'the index.', SQLERRM;
        END $$
    """)
    op.execute("""
        CREATE INDEX idx_chunks_fts ON document_chunks USING gin (fts)
    """)
    op.execute("""
        CREATE INDEX idx_chunks_doc ON document_chunks (document_id)
    """)

    # --- Query audit (ZDR-compliant: metadata only, no raw documents) ---
    op.execute("""
        CREATE TABLE query_audit (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id    UUID NOT NULL REFERENCES tenants(id),
            user_ref     TEXT NOT NULL,
            question_hash TEXT NOT NULL,
            filters      JSONB,
            retrieved_chunk_ids UUID[],
            similarity_scores NUMERIC[],
            threshold_passed BOOLEAN,
            answer_text  TEXT,
            citations    JSONB,
            latency_ms   INT,
            created_at   TIMESTAMPTZ DEFAULT now()
        )
    """)

    # --- Row-Level Security: tenant isolation (enforce now, one tenant today) ---
    op.execute("ALTER TABLE documents ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON documents
            USING (tenant_id = current_setting('app.tenant_id')::UUID)
    """)
    op.execute("""
        CREATE POLICY tenant_isolation ON document_chunks
            USING (tenant_id = current_setting('app.tenant_id')::UUID)
    """)

    # --- Seed: tenant zero (Task 1.2 DoD) + its shared jurisprudence vault ---
    op.execute(f"""
        INSERT INTO tenants (id, name, slug, jurisdiction) VALUES
            ('{TENANT_AETOES}', 'Aetoes Legal', 'aetoes', 'NG')
    """)
    op.execute(f"""
        INSERT INTO vaults (id, tenant_id, vault_type, name, is_shared) VALUES
            ('{VAULT_JURIS_NG}', '{TENANT_AETOES}', 'juris', 'Nigerian Juris OS', TRUE)
    """)


def downgrade() -> None:
    for table in (
        "query_audit",
        "document_chunks",
        "documents",
        "vaults",
        "tenants",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
