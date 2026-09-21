"""Practice operations — invoices, line items, payments (Addendum §9.1, task 3.9 sub-task 2).

DDL transcribed from docs/RedCase-Feature-Addendum.md §9.1 (source of truth).
Additions beyond the doc, recorded per HANDOFF.md rule 3:

1. §9.1's DDL creates invoices/payments WITHOUT tenant RLS. HANDOFF 2.5 (tenant
   scoping) is non-negotiable in every file, so tenant_isolation is added on all
   three tables (USING + WITH CHECK, no GUC default — fails closed), same shape as
   the rest of the chain.
2. §9.1's invoices has NO line-items table, but an invoice is a projection of the
   billed time_entries (§9.1 feature (b): "one-click invoice from unbilled
   entries"). invoice_line_items is added to (a) snapshot the description/amount at
   invoice time, (b) bind each invoice to the exact time_entries it billed, and
   (c) let receivables/aging and PDF export render per-line detail. Each invoice must
   reference at least one line item (a 0-amount invoice is not a bill).
3. §9.1's invoices.status allows DRAFT/SENT/PARTIAL/PAID/WRITTEN_OFF as a
   bare CHECK. Kept verbatim. Payments drive PARTIAL vs PAID (in the router, per
   the doc's payment-recording semantics). sent_at is added to record when DRAFT→SENT
   happened (the aging clock should start at send, not at draft creation).
4. §9.1's payments.tenant_id is a bare NOT NULL (no REFERENCES). tenant_id is
   duplicated onto the row (HANDOFF 2.5) — explicit column, same rationale as
   invoices/time_entries. invoice_id FK -> invoices(id); an FK does not carry over to
   the tenant, so the router validates invoice tenancy before inserting a payment.
5. Indexes: payments (tenant_id, invoice_id) and line_items (tenant_id, invoice_id)
   for per-invoice aggregation and aging queries; invoice_line_items has a UNIQUE
   (invoice_id, time_entry_id) so a time entry is billed at most once.

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-21
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE invoices (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID NOT NULL REFERENCES tenants(id),
            matter_id  UUID NOT NULL REFERENCES matters(id),
            number     TEXT NOT NULL,
            status     TEXT NOT NULL DEFAULT 'DRAFT'
                       CHECK (status IN ('DRAFT','SENT','PARTIAL','PAID','WRITTEN_OFF')),
            amount_ngn  NUMERIC(14,2) NOT NULL,
            due_date    DATE,
            sent_at    TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE (tenant_id, number)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE invoice_line_items (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id     UUID NOT NULL REFERENCES tenants(id),
            invoice_id   UUID NOT NULL REFERENCES invoices(id),
            time_entry_id UUID NOT NULL REFERENCES time_entries(id),
            description  TEXT NOT NULL,
            minutes     INT NOT NULL,
            rate_ngn    NUMERIC(12,2),
            amount_ngn   NUMERIC(14,2) NOT NULL,
            UNIQUE (invoice_id, time_entry_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE payments (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID NOT NULL,
            invoice_id  UUID NOT NULL REFERENCES invoices(id),
            amount_ngn  NUMERIC(14,2) NOT NULL,
            method      TEXT,
            reference  TEXT,
            paid_at    TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    for table, idx in (
        ("invoices", "invoices_matter_idx"),
        ("invoice_line_items", "invoice_line_items_invoice_idx"),
        ("payments", "payments_invoice_idx"),
    ):
        col = "matter_id" if table == "invoices" else "invoice_id"
        op.execute(
            f"CREATE INDEX {idx} ON {table} (tenant_id, {col})"
        )
    for table in ("invoices", "invoice_line_items", "payments"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
                USING (tenant_id = current_setting('app.tenant_id')::UUID)
                WITH CHECK (tenant_id = current_setting('app.tenant_id')::UUID)
            """
        )


def downgrade() -> None:
    for table in ("payments", "invoice_line_items", "invoices"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP INDEX IF EXISTS payments_invoice_idx")
    op.execute("DROP INDEX IF EXISTS invoice_line_items_invoice_idx")
    op.execute("DROP INDEX IF EXISTS invoices_matter_idx")
    op.execute("DROP TABLE IF EXISTS payments")
    op.execute("DROP TABLE IF EXISTS invoice_line_items")
    op.execute("DROP TABLE IF EXISTS invoices")
