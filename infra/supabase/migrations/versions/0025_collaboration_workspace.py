"""User collaboration workspace records.

Merge migration for the two existing 0024 heads. Pins contain references only;
no document or message body is copied into this table.
"""
from collections.abc import Sequence
from alembic import op

revision: str = "0025"
down_revision: str | Sequence[str] = ("0024", "0024d")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE user_pins (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id),
            user_ref TEXT NOT NULL,
            resource_type TEXT NOT NULL CHECK (resource_type IN ('CHANNEL','MESSAGE','THREAD','ANALYSIS','MATTER')),
            resource_id UUID NOT NULL,
            label TEXT NOT NULL CHECK (char_length(label) BETWEEN 1 AND 200),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, user_ref, resource_type, resource_id)
        )
    """)
    op.execute("CREATE INDEX user_pins_user_idx ON user_pins (tenant_id, user_ref, created_at DESC)")
    op.execute("ALTER TABLE user_pins ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_user_isolation ON user_pins
        USING (tenant_id = current_setting('app.tenant_id')::UUID AND user_ref = current_setting('app.user_ref'))
        WITH CHECK (tenant_id = current_setting('app.tenant_id')::UUID AND user_ref = current_setting('app.user_ref'))
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_user_isolation ON user_pins")
    op.execute("ALTER TABLE user_pins DISABLE ROW LEVEL SECURITY")
    op.execute("DROP TABLE IF EXISTS user_pins")
