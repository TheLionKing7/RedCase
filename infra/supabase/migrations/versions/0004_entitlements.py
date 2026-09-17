"""Entitlements + monetization schema — Feature-Addendum §6.

DDL transcribed from docs/RedCase-Feature-Addendum.md §6 (source of truth).
Additions beyond the doc, recorded per HANDOFF.md rule 3:
  * §6 says nothing about RLS on either table. Convention 5 (tenant
    scoping) is non-negotiable, so both get tenant_isolation policies
    (USING + WITH CHECK, no GUC default — fails closed), same pattern as
    migrations 0002/0003.
  * Seed row for tenant ``aetoes``: plan PREMIUM, max_seats 10. Tenant
    zero builds and demos the Workbench (Step A /analyze needs
    workbench.analyze). ``current_seats`` is the billing anchor per §6
    and is maintained by the billing integration, not by this schema.
  * ``entitlement_events.tenant_id`` deliberately has no FK in §6's DDL —
    kept verbatim (audit-grade append-only log; an FK would tie it to
    tenant lifecycle). RLS still scopes reads.

Seat-counting note (reported to owner): §6's enforcement counts "active
users with clearance in ('PARTNER','SENIOR','STAFF')", but no users/
clearance table exists in Phase 1 (users are Supabase Auth records;
clearance provisioning is Phase 2). The Phase 1 gate therefore checks the
billing anchors (current_seats vs max_seats) only; clearance-based
counting lands with Phase 2 user provisioning.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-17

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_AETOES = "a0000001-0000-4000-8000-000000000001"


def upgrade() -> None:
    # --- Subscriptions (billing anchor) — §6 verbatim ---
    op.execute("""
        CREATE TABLE subscriptions (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID NOT NULL UNIQUE REFERENCES tenants(id),
            plan        TEXT NOT NULL DEFAULT 'CORE' CHECK (plan IN ('CORE','PREMIUM')),
            max_seats   INT NOT NULL DEFAULT 0,        -- 0 = unlimited (legacy) — avoid
            current_seats INT NOT NULL DEFAULT 0,
            status      TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','PAST_DUE','SUSPENDED')),
            renews_at   DATE,
            created_at  TIMESTAMPTZ DEFAULT now()
        )
    """)

    # --- Entitlement gate log (audit-grade) — §6 verbatim ---
    op.execute("""
        CREATE TABLE entitlement_events (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID NOT NULL,
            user_ref    TEXT NOT NULL,
            feature     TEXT NOT NULL,               -- 'workbench.analyze','workbench.chat'
            decision    TEXT NOT NULL,               -- 'ALLOW','DENY_SEAT','DENY_PLAN','DENY_SUSPENDED'
            created_at  TIMESTAMPTZ DEFAULT now()
        )
    """)

    # --- Row-Level Security (convention 5; see header conflicts) ---
    op.execute("ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE entitlement_events ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON subscriptions
            USING (tenant_id = current_setting('app.tenant_id')::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id')::UUID)
    """)
    op.execute("""
        CREATE POLICY tenant_isolation ON entitlement_events
            USING (tenant_id = current_setting('app.tenant_id')::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id')::UUID)
    """)

    # --- Seed: tenant zero gets a premium workbench (see header) ---
    op.execute(f"""
        INSERT INTO subscriptions (tenant_id, plan, max_seats, current_seats, status)
        VALUES ('{TENANT_AETOES}', 'PREMIUM', 10, 0, 'ACTIVE')
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON entitlement_events")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON subscriptions")
    op.execute("ALTER TABLE entitlement_events DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE subscriptions DISABLE ROW LEVEL SECURITY")
    op.execute("DROP TABLE IF EXISTS entitlement_events")
    op.execute("DROP TABLE IF EXISTS subscriptions")
