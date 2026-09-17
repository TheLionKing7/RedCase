"""query_audit RLS — tenant isolation policy for the audit table.

CONFLICT RECORDED (HANDOFF.md rule 3, reported to owner): Phase1-Design 2.1's
DDL creates query_audit WITHOUT enabling RLS (only documents and
document_chunks get policies). HANDOFF.md 2.5 (tenant scoping) is one of the
six non-negotiable conventions in every file — an audit table readable across
tenants violates it, so this migration adds the policy the DDL omitted. The
policy mirrors the other tables exactly: no default on the GUC, so an
unset app.tenant_id fails closed.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-17

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE query_audit ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON query_audit
            USING (tenant_id = current_setting('app.tenant_id')::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id')::UUID)
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON query_audit")
    op.execute("ALTER TABLE query_audit DISABLE ROW LEVEL SECURITY")
