"""Firm members (personnel identity), access-request flow + analysis chaining —
IA spec §1.6/§1.7 (S10-4).

Three S10-4 / IA-pass-1 additions, all thin:

  * ``firm_members`` — the personnel register: every licensed user's REAL name tied to
    their Supabase ``user_ref`` within a tenant. This is the user's personnel identity
    (e.g. "Tosin Adebayo · Aetoes Legal") — deliberately SEPARATE from the agent
    persona (agent_personas, S10-2): one is the human's real name, the other the
    assistant's constructed persona they author. Rows are provisioned at invite-accept
    (name is captured there) and seeded for tenant zero's managing partner so the chrome
    (header / home eyebrow) shows a real name, never "ANON".

  * ``access_requests`` — the §1.6 privilege workflow: request → grantor approves →
    router writes a ``document_grants`` row + audit. No admin begging; the privilege
    model stays airtight and self-service.

  * ``document_analyses.parent_analysis_id`` — the §1.7 analysis-gardening edge:
    "Re-analyze with ▾ (pack chaining)". A new analysis on the SAME document with a
    different pack linked by parent id; full provenance, no new pipeline machinery.

RLS: firm_members is tenant-scoped (every member reads the firm register; the router
gates who may edit). access_requests is tenant-scoped; per-user request/decide
authority is a router concern (RLS covers tenant isolation, never authorizes — a requester
may not self-approve). document_analyses.parent_analysis_id is metadata; the tenant
isolation policy (0003) already scopes it.

ZDR: firm_members.full_name is the user's real personnel name (display metadata, PII — never
logged). access_requests.reason is short operational text; document_analyses holds metadata only.

Revision ID: 0024  Revises: 0023
Create Date: 2026-09-24
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Personnel register (real human names; distinct from agent personas) ---
    op.execute(
        """
        CREATE TABLE firm_members (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID NOT NULL REFERENCES tenants(id),
            user_ref    TEXT NOT NULL,
            full_name   TEXT NOT NULL,
            role       TEXT,
            clearance  TEXT,
            created_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE (tenant_id, user_ref)
        )
        """
    )
    op.execute("ALTER TABLE firm_members ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON firm_members
            USING (tenant_id = current_setting('app.tenant_id')::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id')::UUID)
        """
    )
    op.execute(
        "CREATE INDEX firm_members_user_idx ON firm_members (tenant_id, user_ref)"
    )
    op.execute(
        "INSERT INTO firm_members (tenant_id, user_ref, full_name, role, clearance)"
        " VALUES ('a0000001-0000-4000-8000-000000000001',"
        " 'mp-aetoes', 'Tosin Adebayo', 'Managing Partner', 'PARTNER')"
    )
    # --- Access-request flow (sec1.6) ---
    op.execute(
        """
        CREATE TABLE access_requests (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID NOT NULL REFERENCES tenants(id),
            document_id UUID NOT NULL REFERENCES documents(id),
            requester_ref TEXT NOT NULL,
            grantee_ref  TEXT NOT NULL,
            grant_level TEXT NOT NULL DEFAULT 'READ'
                CHECK (grant_level IN ('READ','ANNOTATE')),
            reason     TEXT,
            status     TEXT NOT NULL DEFAULT 'PENDING'
                CHECK (status IN ('PENDING','APPROVED','DENIED')),
            decided_by  TEXT,
            decided_at  TIMESTAMPTZ,
            created_at  TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute("ALTER TABLE access_requests ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON access_requests
            USING (tenant_id = current_setting('app.tenant_id')::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id')::UUID)
        """
    )
    op.execute(
        "CREATE INDEX access_requests_status_idx ON access_requests (tenant_id, status)"
    )

    # --- Analysis chaining (sec1.7) ---
    op.execute(
        "ALTER TABLE document_analyses ADD COLUMN parent_analysis_id UUID"
        " REFERENCES document_analyses(id)"
    )
    op.execute(
        "CREATE INDEX analyses_parent_idx"
        " ON document_analyses (tenant_id, parent_analysis_id) WHERE parent_analysis_id IS NOT NULL"
    )

    op.execute(
        """
        DO $do$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'redcase_app') THEN
            GRANT SELECT, INSERT, UPDATE ON firm_members TO redcase_app;
            GRANT SELECT, INSERT, UPDATE ON access_requests TO redcase_app;
          END IF;
        END $do$
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS analyses_parent_idx")
    op.execute(
        "ALTER TABLE document_analyses DROP COLUMN IF EXISTS parent_analysis_id"
    )
    op.execute("DROP INDEX IF EXISTS access_requests_status_idx")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON access_requests")
    op.execute("ALTER TABLE access_requests DISABLE ROW LEVEL SECURITY")
    op.execute("DROP TABLE IF EXISTS access_requests")
    op.execute("DROP INDEX IF EXISTS firm_members_user_idx")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON firm_members")
    op.execute("ALTER TABLE firm_members DISABLE ROW LEVEL SECURITY")
    op.execute("DROP TABLE IF EXISTS firm_members")
