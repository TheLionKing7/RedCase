"""Court Diary entries and scheduler-safe notification state."""
from collections.abc import Sequence

from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE court_diary_entries (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      tenant_id UUID NOT NULL REFERENCES tenants(id),
      matter_id UUID NOT NULL REFERENCES matters(id),
      source_document_id UUID REFERENCES documents(id),
      event_id UUID REFERENCES deadline_events(id) ON DELETE SET NULL,
      title TEXT NOT NULL,
      entry_type TEXT NOT NULL CHECK (entry_type IN ('HEARING','FILING','MENTION','OTHER')),
      starts_at TIMESTAMPTZ NOT NULL,
      ends_at TIMESTAMPTZ,
      courtroom TEXT,
      judge TEXT,
      notes TEXT,
      status TEXT NOT NULL DEFAULT 'SCHEDULED'
        CHECK (status IN ('SCHEDULED','COMPLETED','ADJOURNED','CANCELLED')),
      created_by TEXT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      CHECK (ends_at IS NULL OR ends_at >= starts_at)
    )
    """)
    op.execute("CREATE INDEX court_diary_tenant_date ON court_diary_entries (tenant_id, starts_at, status)")
    op.execute("ALTER TABLE court_diary_entries ENABLE ROW LEVEL SECURITY")
    op.execute("""
      CREATE POLICY tenant_isolation ON court_diary_entries
      USING (tenant_id = current_setting('app.tenant_id')::UUID)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS court_diary_entries")