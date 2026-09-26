"""Allow saved draft analyses in the Workbench."""

from collections.abc import Sequence

from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE document_analyses DROP CONSTRAINT document_analyses_status_check")
    op.execute("ALTER TABLE document_analyses ADD CONSTRAINT document_analyses_status_check CHECK (status IN ('DRAFT','RUNNING','COMPLETE','FAILED','NEEDS_REVIEW'))")


def downgrade() -> None:
    op.execute("ALTER TABLE document_analyses DROP CONSTRAINT document_analyses_status_check")
    op.execute("ALTER TABLE document_analyses ADD CONSTRAINT document_analyses_status_check CHECK (status IN ('RUNNING','COMPLETE','FAILED','NEEDS_REVIEW'))")
