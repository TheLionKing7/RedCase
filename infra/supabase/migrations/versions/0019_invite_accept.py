"""Invite accept (invitee bootstrap) - Part 3 Slice 1 backend close.

Extends the invitation surface (migration 0018) with the columns the invitee
bootstrap path needs to complete a seat:

  * invite_token_hash       - SHA-256 (subkeyed) digest of the raw invite token,
                            UNIQUE. Only the digest is stored, so a DB leak never
                            yields a usable invite link (same convention as
                            firm_signups.verify_token_hash).
  * invite_token_expires_at - the invite link's lifetime.
  * accepted_at            - set on successful accept (non-NULL == used).
  * accepted_user_ref      - Supabase user id that claimed the seat.
  * accepted_clearance    - the RLS clearance GRANTED (recorded for audit; the
                            role->clearance mapping is server-derived, never client
                            input).

And ``redcase_claim_invite`` - a SECURITY DEFINER function that atomically
claims a PENDING invite by token hash and returns its provisioning details.

Why SECURITY DEFINER: ``POST /v1/invites/accept`` is UNAUTHENTICATED (it IS
the bootstrap path), so there is no tenant JWT to set ``app.tenant_id`` before
reading ``firm_invites`` - the token lookup is the ONLY way to learn the tenant.
The function is owned by the migration/owner role (bypasses RLS inside its body),
is narrow (reads exactly one invite by hash, claims it), and executes with a locked
``search_path`` so it cannot be hijacked. Single-use is enforced in SQL: the UPDATE
only matches ``status = 'PENDING'``, so a second accept matches zero rows and is
rejected.

ZDR: emails are PII - the function never logs; it returns columns to the caller,
which writes the audit row per the Part 3 spec.

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-21

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE firm_invites"
        " ADD COLUMN invite_token_hash TEXT UNIQUE,"
        " ADD COLUMN invite_token_expires_at TIMESTAMPTZ,"
        " ADD COLUMN accepted_at TIMESTAMPTZ,"
        " ADD COLUMN accepted_user_ref TEXT,"
        " ADD COLUMN accepted_clearance TEXT"
    )

    # Atomic single-use claim. SECURITY DEFINER so an unauthenticated caller can
    # resolve a token to its invite without a tenant GUC; audit/email handling stays
    # in the router.
    op.execute(
        """
        CREATE FUNCTION redcase_claim_invite(p_token_hash TEXT, p_now TIMESTAMPTZ)
        RETURNS TABLE (
            r_id UUID,
            r_tenant_id UUID,
            r_invited_email TEXT,
            r_role TEXT,
            r_clearance TEXT,
            r_invited_by TEXT,
            r_status TEXT,
            r_accepted_at TIMESTAMPTZ
        )
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = public
        AS $fn$
        BEGIN
            RETURN QUERY
            UPDATE firm_invites
               SET status = 'ACCEPTED',
                   accepted_at = p_now
             WHERE invite_token_hash = p_token_hash
               AND status = 'PENDING'
               AND (invite_token_expires_at IS NULL
                    OR invite_token_expires_at > p_now)
            RETURNING firm_invites.id, firm_invites.tenant_id,
                      firm_invites.invited_email, firm_invites.role,
                      firm_invites.clearance, firm_invites.invited_by,
                      firm_invites.status, firm_invites.accepted_at;
        END;
        $fn$
        """
    )
    # Grant EXECUTE to the app role ONLY if it exists. `redcase_app` is a
    # non-superuser APP role created by the test harness (apps/api/tests/conftest.py)
    # and, where applicable, by production cluster provisioning. On the live Supabase
    # project the app connects with a different role name, so an unconditional GRANT
    # would raise `role "redcase_app" does not exist` and roll back the whole
    # migration (defect caught on first deploy). Guarding on pg_roles keeps the
    # migrate step idempotent across both environments (HANDOFF.md 3).
    op.execute(
        "DO $do$ BEGIN"
        " IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'redcase_app') THEN"
        "   EXECUTE 'GRANT EXECUTE ON FUNCTION redcase_claim_invite(TEXT, TIMESTAMPTZ) TO redcase_app';"
        " END IF;"
        " END $do$"
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS redcase_claim_invite(TEXT, TIMESTAMPTZ)")
    op.execute(
        "ALTER TABLE firm_invites"
        " DROP COLUMN IF EXISTS invite_token_hash,"
        " DROP COLUMN IF EXISTS invite_token_expires_at,"
        " DROP COLUMN IF EXISTS accepted_at,"
        " DROP COLUMN IF EXISTS accepted_user_ref,"
        " DROP COLUMN IF EXISTS accepted_clearance"
    )
