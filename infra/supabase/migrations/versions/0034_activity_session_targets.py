"""Allow activity sessions to be associated with a matter or work area."""

from collections.abc import Sequence

from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE activity_sessions ADD COLUMN target_type TEXT")
    op.execute("ALTER TABLE activity_sessions ADD COLUMN target_ref TEXT")
    op.execute(
        "ALTER TABLE activity_sessions ADD CONSTRAINT activity_sessions_target_pair_check "
        "CHECK ((target_type IS NULL) = (target_ref IS NULL))"
    )
    op.execute(
        "CREATE INDEX activity_sessions_target_idx ON activity_sessions "
        "(tenant_id, user_ref, target_type, target_ref, started_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS activity_sessions_target_idx")
    op.execute(
        "ALTER TABLE activity_sessions DROP CONSTRAINT IF EXISTS activity_sessions_target_pair_check"
    )
    op.execute("ALTER TABLE activity_sessions DROP COLUMN IF EXISTS target_ref")
    op.execute("ALTER TABLE activity_sessions DROP COLUMN IF EXISTS target_type")