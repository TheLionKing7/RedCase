"""Store references to outputs reviewed by Assistant without copying output text."""

from collections.abc import Sequence

from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE assistant_messages ADD COLUMN source_bench TEXT")
    op.execute("ALTER TABLE assistant_messages ADD COLUMN source_type TEXT")
    op.execute("ALTER TABLE assistant_messages ADD COLUMN source_id UUID")
    op.execute("ALTER TABLE assistant_messages ADD COLUMN source_label TEXT")
    op.execute("CREATE INDEX assistant_messages_source_idx ON assistant_messages (tenant_id, source_id) WHERE source_id IS NOT NULL")
    op.execute("""
        ALTER TABLE assistant_messages ADD CONSTRAINT assistant_messages_source_type_check
        CHECK (source_type IS NULL OR source_type = 'analysis')
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS assistant_messages_source_idx")
    op.execute("ALTER TABLE assistant_messages DROP CONSTRAINT IF EXISTS assistant_messages_source_type_check")
    op.execute("ALTER TABLE assistant_messages DROP COLUMN IF EXISTS source_label")
    op.execute("ALTER TABLE assistant_messages DROP COLUMN IF EXISTS source_id")
    op.execute("ALTER TABLE assistant_messages DROP COLUMN IF EXISTS source_type")
    op.execute("ALTER TABLE assistant_messages DROP COLUMN IF EXISTS source_bench")