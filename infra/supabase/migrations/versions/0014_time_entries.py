"""Practice operations — time_entries (Addendum §9.1, task 3.9 sub-task 1).

DDL transcribed from docs/RedCase-Feature-Addendum.md §9.1 (source of truth).
Additions beyond the doc, recorded per HANDOFF.md rule 3:
  * §9.1's DDL creates time_entries WITHOUT tenant RLS. HANDOFF 2.5 (tenant
    scoping) is non-negotiable in every file, so tenant_isolation is added
    (USING + WITH CHECK, no GUC default — fails closed), same shape as the
    rest of the chain.
  * matter_id FK -> matters(id) exists (matters landed in 0008). tenant_id is
    duplicated onto the row (HANDOFF 2.5) even though an FK -> matters could
    imply it — RLS keys on the row's own tenant_id and FKs bypass RLS, so the
    explicit column is kept verbatim (same rationale as invoices/payments in §9.1).
  * Index on (tenant_id, matter_id) so matter-scoped time lists and per-matter
    invoicing (sub-task 2) are efficient.
  * Idempotency key: clients retry at-least-once (Slack-style / client timer
    double-submit). A unique index on (tenant_id, idempotency_key) collapses
    duplicates to one entry, scoped per tenant — same deviation rationale for the
    §7.1 channel idempotency key (a global unique would let one tenant's key
    collide with another's).

The default instruction "rate_ngn NULL = use matter default rate" is preserved
verbatim (matters carries no per-row rate until invoicing sub-task 2 decides where
the default lives; NULL simply defers to the matter/invoice default resolution).

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-20
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE time_entries (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id      UUID NOT NULL REFERENCES tenants(id),
            matter_id     UUID NOT NULL REFERENCES matters(id),
            user_ref      TEXT NOT NULL,
            description  TEXT NOT NULL,
            minutes     INT NOT NULL CHECK (minutes > 0),
            rate_ngn    NUMERIC(12,2),            -- NULL = use matter default rate
            billed      BOOLEAN DEFAULT FALSE,
            idempotency_key TEXT,
            created_at  TIMESTAMPTZ DEFAULT now(),
            worked_at  TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX time_entries_matter_idx
            ON time_entries (tenant_id, matter_id)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX time_entries_idempotency_key
            ON time_entries (tenant_id, idempotency_key)
        """
    )
    op.execute("ALTER TABLE time_entries ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON time_entries
            USING (tenant_id = current_setting('app.tenant_id')::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id')::UUID)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON time_entries")
    op.execute("DROP INDEX IF EXISTS time_entries_idempotency_key")
    op.execute("DROP INDEX IF EXISTS time_entries_matter_idx")
    op.execute("ALTER TABLE time_entries DISABLE ROW LEVEL SECURITY")
    op.execute("DROP TABLE IF EXISTS time_entries")
