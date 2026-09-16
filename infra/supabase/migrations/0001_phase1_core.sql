BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE tenants (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name        TEXT NOT NULL,
            slug        TEXT UNIQUE NOT NULL,
            jurisdiction TEXT NOT NULL DEFAULT 'NG',
            created_at  TIMESTAMPTZ DEFAULT now()
        );

CREATE TABLE vaults (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID NOT NULL REFERENCES tenants(id),
            vault_type  TEXT NOT NULL CHECK (vault_type IN ('firm', 'juris')),
            name        TEXT NOT NULL,
            is_shared   BOOLEAN DEFAULT FALSE,
            created_at  TIMESTAMPTZ DEFAULT now()
        );

CREATE TABLE documents (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id    UUID NOT NULL REFERENCES tenants(id),
            vault_id     UUID NOT NULL REFERENCES vaults(id),
            case_title   TEXT NOT NULL,
            citation     TEXT NOT NULL,
            citation_norm TEXT GENERATED ALWAYS AS (upper(regexp_replace(citation, '\s+', ' ', 'g'))) STORED,
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
        );

CREATE INDEX idx_documents_meta ON documents
            USING btree (tenant_id, court_level, year);

CREATE INDEX idx_documents_ratio ON documents USING gin (ratio_decidendi);

CREATE INDEX idx_documents_topics ON documents USING gin (legal_topics);

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
        );

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
        END $$;

CREATE INDEX idx_chunks_fts ON document_chunks USING gin (fts);

CREATE INDEX idx_chunks_doc ON document_chunks (document_id);

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
        );

ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON documents
            USING (tenant_id = current_setting('app.tenant_id')::UUID);

CREATE POLICY tenant_isolation ON document_chunks
            USING (tenant_id = current_setting('app.tenant_id')::UUID);

INSERT INTO tenants (id, name, slug, jurisdiction) VALUES
            ('a0000001-0000-4000-8000-000000000001', 'Aetoes Legal', 'aetoes', 'NG');

INSERT INTO vaults (id, tenant_id, vault_type, name, is_shared) VALUES
            ('b0000001-0000-4000-8000-000000000001', 'a0000001-0000-4000-8000-000000000001', 'juris', 'Nigerian Juris OS', TRUE);

INSERT INTO alembic_version (version_num) VALUES ('0001') RETURNING alembic_version.version_num;

COMMIT;

