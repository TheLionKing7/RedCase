"""Public firm signup + invites - onboarding funnel (HANDOFF §4 tenant growth surface).

Creates the system's first UNAUTHENTICATED write path, so every table it
touches is designed to resist bot-driven tenant flooding (the entitlement-ledger
poisoning DoD):

  * firm_signups  - a row per application, keyed by NORMALIZED (lowercased,
                    trimmed) email + unique index. A duplicate application is
                    rejected at the database level, not merely by the router.
                    Status gates lifecycle: PENDING_VERIFICATION -> VERIFIED ->
                    ACTIVE (REJECTED aborts). A signup NEVER auto-creates a
                    tenant: the tenant row is provisioned only by the verification
                    step (see the router), preserving the "email verification
                    before the tenant activates" invariant.
  * signup_audit - append-only, audit-grade provisioning log (UUID id, step,
                    actor). Every step of the funnel (apply, verify, provision,
                    invite) writes exactly one row. Revoked UPDATE/DELETE from the
                    app role in conftest's grant step to make immutability a
                    database grant, same contract as query_audit /
                    entitlement_events.
  * firm_invites - tenant seat-granting + clearance-from-role mapping surface.
                    Each row carries the invited email, role (the firm-facing
                    title) and clearance (the RLS ladder value the invitee's
                    Supabase claim will carry: STAFF|SENIOR|PARTNER|ADMIN).
                    Seats are consumed at INVITE time against subscriptions (the
                    monetization schema's live exercise) - see the seat algorithm
                    in routers/invites.py.

ZDR: emails are PII and are never written to logs. Signup_audit carries
ids, slugs, and step names only.

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-21

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE firm_signups (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email       TEXT NOT NULL,
            firm_name   TEXT NOT NULL,
            jurisdiction TEXT NOT NULL DEFAULT 'NG',
            status      TEXT NOT NULL DEFAULT 'PENDING_VERIFICATION'
                         CHECK (status IN ('PENDING_VERIFICATION','VERIFIED','ACTIVE','REJECTED')),
            tenant_id   UUID REFERENCES tenants(id),
            created_at  TIMESTAMPTZ DEFAULT now(),
            verified_at TIMESTAMPTZ,
            -- Email-verification gate (Part 2 DoD): the account is NOT
            -- activated until the holder of this token confirms the address.
            -- Only the SHA-256 hash is stored, so a DB leak never yields a
            -- usable token. Written once at apply, nulled on successful verify.
            verify_token_hash TEXT UNIQUE,
            verify_token_expires_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE UNIQUE INDEX firm_signups_email_uq ON firm_signups (email)")

    op.execute("""
        CREATE TABLE signup_audit (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID REFERENCES tenants(id),
            step        TEXT NOT NULL,
            actor       TEXT NOT NULL DEFAULT 'system',
            detail      TEXT,
            created_at  TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("ALTER TABLE signup_audit ENABLE ROW LEVEL SECURITY")

    # Missing-ok current_setting: the UNAUTHENTICATED apply path writes this row
    # with tenant_id NULL and NO app.tenant_id GUC set - the single-arg form would
    # raise UnrecognizedConfigurationParameterException (migration 0008 note). The NULL
    # branch keeps the pre-provision 'apply' step writable and the tenant branch scopes
    # authenticated reads. WITH CHECK mirrors USING so INSERTs comply.
    op.execute("""
        CREATE POLICY tenant_isolation ON signup_audit
            USING (tenant_id IS NULL
                  OR tenant_id = current_setting('app.tenant_id', true)::UUID)
            WITH CHECK (tenant_id IS NULL
                      OR tenant_id = current_setting('app.tenant_id', true)::UUID)
    """)

    op.execute("""
        CREATE TABLE firm_invites (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id    UUID NOT NULL REFERENCES tenants(id),
            invited_email TEXT NOT NULL,
            role         TEXT NOT NULL
                          CHECK (role IN ('PARTNER','SENIOR','ASSOCIATE','STAFF')),
            clearance    TEXT NOT NULL
                          CHECK (clearance IN ('STAFF','SENIOR','PARTNER','ADMIN')),
            status       TEXT NOT NULL DEFAULT 'PENDING'
                          CHECK (status IN ('PENDING','ACCEPTED','REVOKED')),
            invited_by   TEXT NOT NULL,
            created_at   TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("ALTER TABLE firm_invites ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON firm_invites
            USING (tenant_id = current_setting('app.tenant_id')::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id')::UUID)
    """)
    op.execute("""
        CREATE UNIQUE INDEX firm_invites_email_pending_uq
            ON firm_invites (tenant_id, invited_email)
            WHERE status = 'PENDING'
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON signup_audit")
    op.execute("ALTER TABLE signup_audit DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON firm_invites")
    op.execute("ALTER TABLE firm_invites DISABLE ROW LEVEL SECURITY")
    op.execute("DROP TABLE IF EXISTS firm_invites")
    op.execute("DROP TABLE IF EXISTS signup_audit")
    op.execute("DROP TABLE IF EXISTS firm_signups")
