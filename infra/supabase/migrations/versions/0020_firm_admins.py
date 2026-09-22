"""Firm admins + admin-capability ledger — Addendum §8.5 (audit H3).

Implements the SURFACE MODEL ruling: admin capability is an ORTHOGONAL dimension
to clearance. `is_firm_admin` is a separate, grantable flag carried on the
Supabase JWT `app_metadata` claim (fail-closed false in deps.py), NOT derived
from clearance. This migration creates the append-only ledger of admin grant/revoke
events (the source of truth for who was granted, when, and by whom), tenant-scoped
under RLS.

  * firm_admins - append-only event log. Each row records one GRANTED/REVOKED
                  event for a user. The live flag lives in Supabase app_metadata;
                  this table is the audit trail. Append-only made a DB grant in
                  conftest (REVOKE UPDATE/DELETE from the app role), same
                  contract as query_audit / entitlement_events / signup_audit.

  * Seed: the managing partner of tenant zero is the default firm admin (a GRANTED
    event), per §8.5 "Managing partner = default admin."

ZDR: user_refs are ids (no names/emails here). Every grant/revoke is a row.

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-22

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_AETOES = "a0000001-0000-4000-8000-000000000001"
# Managing partner of tenant zero = default firm admin (deterministic for tests).
MANAGING_PARTNER_REF = "mp-aetoes"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE firm_admins (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id  UUID NOT NULL REFERENCES tenants(id),
            user_ref   TEXT NOT NULL,
            action     TEXT NOT NULL CHECK (action IN ('GRANTED','REVOKED')),
            granted_by TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute("ALTER TABLE firm_admins ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON firm_admins
            USING (tenant_id = current_setting('app.tenant_id')::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id')::UUID)
        """
    )
    op.execute(
        "CREATE INDEX firm_admins_user_idx ON firm_admins (tenant_id, user_ref)"
    )

    # Default admin: the managing partner of tenant zero (GRANTED event).
    op.execute(
        f"""
        INSERT INTO firm_admins (tenant_id, user_ref, action, granted_by)
        VALUES ('{TENANT_AETOES}', '{MANAGING_PARTNER_REF}', 'GRANTED', 'system')
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON firm_admins")
    op.execute("ALTER TABLE firm_admins DISABLE ROW LEVEL SECURITY")
    op.execute("DROP TABLE IF EXISTS firm_admins")
