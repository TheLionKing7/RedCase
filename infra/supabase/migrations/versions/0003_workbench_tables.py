"""Legal Workbench tables — Feature-Addendum §3.1 (Step A).

CONFLICTS RECORDED (HANDOFF.md rule 3, reported to owner):
  * §3.1's ``document_analyses.matter_id`` references ``matters(id)``, but the
    matters table is Phase 2 and does not exist yet. The column is created
    WITHOUT the FK (nullable, documented) so the migration applies on the
    Phase 1 schema; the FK lands with the Phase 2 migration that creates
    matters.
  * §3.1's DDL says nothing about RLS on the new tables. Convention 5
    (tenant scoping) is non-negotiable, so both tables get tenant_isolation
    policies (USING + WITH CHECK, no GUC default — fails closed), same
    pattern as migration 0002.
  * §3.1 says chat messages reuse query_audit with analysis_id/thread_id
    columns. Step A adds ``analysis_id`` only (analysis audit integration);
    ``thread_id`` lands with Expert Chat (Step D).

Step A scope (owner 2026-09-17): document_analyses + expert_chat_threads
tables; /analyze + /analyses endpoints; ADVERSARIAL_BRIEF pack only.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-17

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Analysis objects (workbench state), Feature-Addendum §3.1 verbatim ---
    op.execute("""
        CREATE TABLE document_analyses (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id    UUID NOT NULL REFERENCES tenants(id),
            document_id  UUID NOT NULL REFERENCES documents(id),
            matter_id    UUID,              -- FK deferred to Phase 2 (matters)
            prompt_pack  TEXT NOT NULL,     -- 'ADVERSARIAL_BRIEF', ...
            status       TEXT NOT NULL DEFAULT 'RUNNING'
                         CHECK (status IN ('RUNNING','COMPLETE','FAILED','NEEDS_REVIEW')),
            output       JSONB,
            confidence   JSONB,
            error        TEXT,              -- worker failure summary (ZDR: no bodies)
            created_by   TEXT NOT NULL,
            created_at   TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE expert_chat_threads (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id    UUID NOT NULL REFERENCES tenants(id),
            analysis_id  UUID NOT NULL REFERENCES document_analyses(id) ON DELETE CASCADE,
            created_by   TEXT NOT NULL,
            created_at   TIMESTAMPTZ DEFAULT now()
        )
    """)

    # --- query_audit link for analysis events (Step A audit integration) ---
    op.execute("""
        ALTER TABLE query_audit
            ADD COLUMN analysis_id UUID REFERENCES document_analyses(id)
    """)

    # --- Row-Level Security (convention 5; see header conflicts) ---
    op.execute("ALTER TABLE document_analyses ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE expert_chat_threads ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON document_analyses
            USING (tenant_id = current_setting('app.tenant_id')::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id')::UUID)
    """)
    op.execute("""
        CREATE POLICY tenant_isolation ON expert_chat_threads
            USING (tenant_id = current_setting('app.tenant_id')::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id')::UUID)
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON expert_chat_threads")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON document_analyses")
    op.execute("ALTER TABLE expert_chat_threads DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE document_analyses DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE query_audit DROP COLUMN IF EXISTS analysis_id")
    op.execute("DROP TABLE IF EXISTS expert_chat_threads")
    op.execute("DROP TABLE IF EXISTS document_analyses")
