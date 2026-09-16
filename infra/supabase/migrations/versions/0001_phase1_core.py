"""Phase 1 core schema — Phase1-Design §2.1 DDL verbatim + tenant seed.

DDL below is transcribed from docs/RedCase-Phase1-Design.md §2.1 (source of
truth). Additions beyond the doc, recorded per HANDOFF.md rule 3:
  * ``CREATE EXTENSION IF NOT EXISTS vector`` — required for VECTOR(3072) /
    hnsw; available on Supabase by default.
  * Seed rows for tenant ``aetoes`` and its shared juris vault — Task 1.2 DoD
    ("seed tenant aetoes"). Fixed UUIDs keep tests and ingestion deterministic.

RLS note: policies use ``current_setting('app.tenant_id')`` with no default, so
any query without the GUC set fails closed (HANDOFF.md §2.2).

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
    # CONFLICT RECORDED (HANDOFF.md rule 3): §2.1 mandates this exact hnsw
    # index on VECTOR(3072). pgvector >= 0.7 (Supabase) supports it; the
    # embedded test Postgres bundles pgvector 0.6.2, whose hnsw cap is 2000
    # dimensions, where the index cannot exist. We create it whenever the
    # installed pgvector supports 3072-dim hnsw and warn-skip otherwise.
    # Production DDL on Supabase is unchanged from the design doc.
    op.execute("""
        DO $$
        DECLARE
            pgv TEXT;
        BEGIN
            SELECT extversion INTO pgv FROM pg_extension WHERE extname = 'vector';
            IF string_to_array(pgv, '.')::int[] >= array[0, 7, 0] THEN
                CREATE INDEX idx_chunks_embedding ON document_chunks
                    USING hnsw (embedding vector_cosine_ops);
            ELSE
                RAISE WARNING
                    'pgvector % has a 2000-dim hnsw cap; skipping idx_chunks_embedding. '
                    'Supabase (pgvector >= 0.7) creates the §2.1 index unchanged.', pgv;
            END IF;
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
