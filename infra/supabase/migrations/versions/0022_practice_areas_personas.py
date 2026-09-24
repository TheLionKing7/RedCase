"""Practice areas + agent personas — Addendum S10.2/S10.3 (S10-2).

Extends the onboarding funnel and the Workbench with two new surfaces:

  * tenant_practice_areas  - the firm's default practice-area lens (tags). Selected
                            during onboarding (step 4, firm defaults). These are the
                            firm-level defaults a lawyer's persona inherits unless the
                            lawyer overrides them at the persona level.
  * agent_personas         - ONE persona per licensed lawyer (§7.2/§10.3). Holds the
                            agent name, rules of engagement, tone preset, and a lawyer-level
                            practice-area override. There is NO model training (ZDR forbids
                            it): these fields are injected INTO the prompt each turn, after the
                            GROUNDED_SYSTEM contract and before retrieval context. The persona
                            can never alter the grounding rules.
                            UNIQUE (tenant_id, owner_ref) enforces one persona per lawyer.

Practice areas are TEXT[]; documents carry legal_topics TEXT[] (migration 0001), so the
lens is a metadata pre-filter (legal_topics && practice_areas) on the assistant's
search_vault_a/b tools and the Similar Cases lens.

RLS: tenant_practice_areas is tenant-scoped (firm-wide read/write; firm-admin writes
during onboarding, reads by all staff). agent_personas is tenant + owner scoped (a lawyer
sees and edits ONLY their own persona — cross-user isolation at the SQL level, DoD 3).

ZDR: agent_personas stores style/preference metadata (name, tone, engagement rules,
practice tags) — no document text, no prompt bodies, no LLM payloads.

Revision ID: 0022  Revises: 0021
Create Date: 2026-09-23
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Firm practice-area defaults (onboarding step 4) ---
    op.execute(
        """
        CREATE TABLE tenant_practice_areas (
            tenant_id UUID NOT NULL REFERENCES tenants(id),
            tag      TEXT NOT NULL,
            PRIMARY KEY (tenant_id, tag)
        )
        """
    )
    op.execute("ALTER TABLE tenant_practice_areas ENABLE ROW LEVEL SECURITY")
    # Firm-wide read (all members) + tenant-scoped write. The per-identity write gate
    # (firm-admin on onboarding) is enforced at the router layer like the KYC admin gate.
    op.execute(
        """
        CREATE POLICY tenant_isolation ON tenant_practice_areas
            USING (tenant_id = current_setting('app.tenant_id')::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id')::UUID)
        """
    )
    op.execute(
        """
        DO $do$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'redcase_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON tenant_practice_areas TO redcase_app;
          END IF;
        END $do$
        """
    )

    # --- Per-lawyer agent persona (Addendum S10.3, verbatim schema) ---
    op.execute(
        """
        CREATE TABLE agent_personas (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID NOT NULL REFERENCES tenants(id),
            owner_ref   TEXT NOT NULL,
            agent_name  TEXT NOT NULL DEFAULT 'Assistant',
            rules_of_engagement TEXT,
            tone_preset TEXT NOT NULL DEFAULT 'PROFESSIONAL'
                CHECK (tone_preset IN ('PROFESSIONAL','CONCISE','NARRATIVE','FORMAL')),
            practice_areas TEXT[],
            created_at  TIMESTAMPTZ DEFAULT now(),
            updated_at  TIMESTAMPTZ DEFAULT now(),
            UNIQUE (tenant_id, owner_ref)
        )
        """
    )
    op.execute(
        "CREATE INDEX agent_personas_owner_idx ON agent_personas (tenant_id, owner_ref)"
    )
    op.execute("ALTER TABLE agent_personas ENABLE ROW LEVEL SECURITY")
    # Tenant + owner isolation: a lawyer sees/writes ONLY their own persona. RLS is the
    # SQL-level defense — lawyer B cannot read lawyer A's persona even with a direct query.
    op.execute(
        """
        CREATE POLICY tenant_owner_isolation ON agent_personas
            USING (tenant_id = current_setting('app.tenant_id')::UUID
                   AND owner_ref = current_setting('app.user_ref'))
            WITH CHECK (tenant_id = current_setting('app.tenant_id')::UUID
                      AND owner_ref = current_setting('app.user_ref'))
        """
    )
    op.execute(
        """
        DO $do$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'redcase_app') THEN
            GRANT SELECT, INSERT, UPDATE ON agent_personas TO redcase_app;
          END IF;
        END $do$
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_owner_isolation ON agent_personas")
    op.execute("ALTER TABLE agent_personas DISABLE ROW LEVEL SECURITY")
    op.execute("DROP TABLE IF EXISTS agent_personas")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON tenant_practice_areas")
    op.execute("ALTER TABLE tenant_practice_areas DISABLE ROW LEVEL SECURITY")
    op.execute("DROP TABLE IF EXISTS tenant_practice_areas")
