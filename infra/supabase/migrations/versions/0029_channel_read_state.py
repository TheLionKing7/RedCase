"""Per-user channel read cursors for trustworthy DM unread counts."""

from collections.abc import Sequence

from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("""
      CREATE TABLE channel_read_state (
        tenant_id UUID NOT NULL REFERENCES tenants(id),
        channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
        user_ref TEXT NOT NULL,
        last_read_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (tenant_id, channel_id, user_ref)
      )
    """)
    op.execute("ALTER TABLE channel_read_state ENABLE ROW LEVEL SECURITY")
    op.execute("""
      CREATE POLICY tenant_isolation ON channel_read_state
      USING (tenant_id = current_setting('app.tenant_id')::UUID)
      WITH CHECK (tenant_id = current_setting('app.tenant_id')::UUID)
    """)
    op.execute("""
      DO $do$
      BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'redcase_app') THEN
          GRANT SELECT, INSERT, UPDATE ON channel_read_state TO redcase_app;
        END IF;
      END $do$
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON channel_read_state")
    op.execute("ALTER TABLE channel_read_state DISABLE ROW LEVEL SECURITY")
    op.execute("DROP TABLE IF EXISTS channel_read_state")