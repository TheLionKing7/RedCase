"""Firm department selections for the onboarding module surface — UX-2."""
from collections.abc import Sequence

from alembic import op

revision: str = "0024d"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE tenant_departments (
            tenant_id UUID NOT NULL REFERENCES tenants(id),
            department TEXT NOT NULL,
            PRIMARY KEY (tenant_id, department)
        )
        """
    )
    op.execute("ALTER TABLE tenant_departments ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON tenant_departments
            USING (tenant_id = current_setting('app.tenant_id')::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id')::UUID)
        """
    )
    op.execute(
        """
        DO $do$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'redcase_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON tenant_departments TO redcase_app;
          END IF;
        END $do$
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON tenant_departments")
    op.execute("ALTER TABLE tenant_departments DISABLE ROW LEVEL SECURITY")
    op.execute("DROP TABLE IF EXISTS tenant_departments")
