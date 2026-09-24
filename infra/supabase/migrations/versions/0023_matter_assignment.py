"""Matter assignment + progress note — S10-3 (Feature-Addendum-S10 §10.4).

S10-3 gives each matter a lead counsel and a free-text progress note, and backs the
Firm Command matter-progress panel. Two additions, both thin:

  * ``matters.assigned_to``  — user_ref (Supabase sub) of the lawyer assigned
                               as lead counsel on the matter. NULL == unassigned.
                               No FK (users live in Supabase Auth, not in-schema —
                               same "ref is a Supabase sub" convention as
                               channel_participants.participant_ref / matters'
                               own caller identity). Tenant-scoped by `matters`
                               itself; NULL means "not yet assigned".
  * ``matters.progress_note`` — free-text status note the firm puts beside a matter
                               in the progress panel. Optional, firm content.

RLS: matters already has tenant_isolation (0008) with USING only. S10-3's assign
endpoint writes assigned_to/progress_note through the app role, so this migration
drops and recreates the policy WITH a WITH CHECK so UPDATE (and finaled INSERT)
stays tenant-scoped — the RLS clause is what stops tenant B from reassigning a
tenant A matter. The panel reads are already scoped by the USING policy.

  * ``matters_assigned_idx`` — tenants see "my matters" and the panel's
    per-lawyer grouping; (tenant_id, assigned_to) is the lookup both need.

ZDR: assigned_to is a ref id; progress_note is firm operational content (like
matter_ref), never logged.

Revision ID: 0023  Revises: 0022
Create Date: 2026-09-23
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE matters"
        " ADD COLUMN assigned_to TEXT,"
        " ADD COLUMN progress_note TEXT"
    )
    op.execute(
        "CREATE INDEX matters_assigned_idx ON matters (tenant_id, assigned_to)"
    )

    # Recreate the 0008 tenant_isolation policy so it carries a WITH CHECK clause.
    # RLS needs WITH CHECK on the row being written (INSERT/UPDATE); without it the
    # app role (which holds UPDATE but not table ownership) cannot write through RLS.
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON matters")
    op.execute(
        "CREATE POLICY tenant_isolation ON matters"
        " USING (tenant_id = current_setting('app.tenant_id')::UUID)"
        " WITH CHECK (tenant_id = current_setting('app.tenant_id')::UUID)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS matters_assigned_idx")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON matters")
    op.execute(
        "CREATE POLICY tenant_isolation ON matters"
        " USING (tenant_id = current_setting('app.tenant_id')::UUID)"
    )
    op.execute(
        "ALTER TABLE matters"
        " DROP COLUMN IF EXISTS progress_note,"
        " DROP COLUMN IF EXISTS assigned_to"
    )
