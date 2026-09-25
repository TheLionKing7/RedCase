"""Non-billable attendance sessions, distinct from practice time_entries."""

from collections.abc import Sequence

from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
      CREATE TABLE activity_sessions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES tenants(id),
        user_ref TEXT NOT NULL,
        area TEXT NOT NULL CHECK (char_length(area) BETWEEN 1 AND 160),
        started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        ended_at TIMESTAMPTZ,
        duration INTEGER CHECK (duration IS NULL OR duration >= 0),
        CHECK (ended_at IS NULL OR ended_at >= started_at)
      )
    """)
    op.execute("CREATE INDEX activity_sessions_user_recent_idx ON activity_sessions (tenant_id, user_ref, started_at DESC)")
    op.execute("CREATE UNIQUE INDEX activity_sessions_one_open_idx ON activity_sessions (tenant_id, user_ref) WHERE ended_at IS NULL")
    op.execute("ALTER TABLE activity_sessions ENABLE ROW LEVEL SECURITY")
    op.execute("""
      CREATE POLICY tenant_isolation ON activity_sessions
      USING (tenant_id = current_setting('app.tenant_id')::UUID
        AND user_ref = current_setting('app.user_ref'))
      WITH CHECK (tenant_id = current_setting('app.tenant_id')::UUID
        AND user_ref = current_setting('app.user_ref'))
    """)
    op.execute("""
      DO $do$
      BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'redcase_app') THEN
          GRANT SELECT, INSERT, UPDATE ON activity_sessions TO redcase_app;
        END IF;
      END $do$
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON activity_sessions")
    op.execute("DROP TABLE IF EXISTS activity_sessions")