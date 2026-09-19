"""Clearance ladder ruling — SENIOR gains CONFIDENTIAL; PARTNER_RESTRICTED grant-gated (owner 2026-09-19).

Task 2.2 addition (2) of the owner brief. Replaces the 0008 clearance
policies (DROP + CREATE — policy expressions are immutable) with the
laddered form, backported into docs/RedCase-Phase2-Design.md 1.2:

  * PUBLIC / FIRM_INTERNAL  -> all same-tenant users (unchanged);
  * CONFIDENTIAL            -> SENIOR, PARTNER, ADMIN clearances, or an
                               explicit document_grants row (NEW: SENIOR
                               gains visibility per the ruling);
  * PARTNER_RESTRICTED      -> document_grants ONLY. Partners and ADMIN
                               no longer get implicit visibility (NEW per
                               the ruling) — the grant ACL is the single
                               door, for everyone.
  * grants open any level for the granted user (document_grants is the
    per-document ACL — that meaning is unchanged).
  * non-firm (Vault B) documents remain classification-blind (unchanged).

Also completes the ACL's write side in SQL (the ruling's 'privilege-
isolation backbone' taken seriously): document_grants gains a
RESTRICTIVE grant_admin policy — grant rows may be created only by
PARTNER/ADMIN clearances, and granted_by must equal the caller's
app.user_ref. A STAFF user attempting to self-grant via SQL is denied at
the database level, not merely by endpoint authorization.

Both restrictive read policies gain WITH CHECK (true): the read layer
must never block ingestion writes (a brand-new PARTNER_RESTRICTED row
cannot satisfy a grant EXISTS against itself — chicken-and-egg). Write
authorization is app-layer, matching Phase 1's tenant_isolation posture
(USING-only, no WITH CHECK) and the recorded 0008 note 5 contract.

Deviations from the 0008 form, per HANDOFF.md rule 3: none beyond the
ruling itself — the ladder replaces the flat 'PARTNER/ADMIN see all'
branch with the two-level form; everything else (vault-type join,
missing-ok GUCs, RESTRICTIVE, qualified documents.id, guard signature)
is preserved verbatim from 0008.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-19

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Laddered clearance on documents (replaces 0008 flat policy) ---
    op.execute("DROP POLICY IF EXISTS vault_a_clearance ON documents")
    op.execute("""
        CREATE POLICY vault_a_clearance ON documents
            AS RESTRICTIVE
            USING ((SELECT v.vault_type FROM vaults v WHERE v.id = vault_id) <> 'firm'
                OR classification_level IN ('PUBLIC','FIRM_INTERNAL')
                OR (classification_level = 'CONFIDENTIAL'
                    AND current_setting('app.user_clearance', true)
                        IN ('SENIOR','PARTNER','ADMIN'))
                OR EXISTS (SELECT 1 FROM document_grants g
                           WHERE g.document_id = documents.id
                             AND g.user_ref = current_setting('app.user_ref', true)))
            WITH CHECK (true)
    """)

    # --- Laddered guard for chunks (replaces 0008 function body) ---
    op.execute("""
        CREATE OR REPLACE FUNCTION vault_type_guard(p_document_id UUID)
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public
        AS $guard$
            SELECT EXISTS (
                SELECT 1 FROM documents d
                WHERE d.id = p_document_id
                  AND ((SELECT v.vault_type FROM vaults v WHERE v.id = d.vault_id) <> 'firm'
                       OR d.classification_level IN ('PUBLIC','FIRM_INTERNAL')
                       OR (d.classification_level = 'CONFIDENTIAL'
                           AND current_setting('app.user_clearance', true)
                               IN ('SENIOR','PARTNER','ADMIN'))
                       OR EXISTS (SELECT 1 FROM document_grants g
                                  WHERE g.document_id = d.id
                                    AND g.user_ref = current_setting('app.user_ref', true)))
            )
        $guard$
    """)

    # --- chunk_privilege gains WITH CHECK (true) for the same reason ---
    op.execute("DROP POLICY IF EXISTS chunk_privilege ON document_chunks")
    op.execute("""
        CREATE POLICY chunk_privilege ON document_chunks
            AS RESTRICTIVE
            USING (vault_type_guard(document_id))
            WITH CHECK (true)
    """)

    # --- Grant administration enforced in SQL (self-grant escalation closed) ---
    op.execute("""
        CREATE POLICY grant_admin ON document_grants
            AS RESTRICTIVE
            USING (true)
            WITH CHECK (current_setting('app.user_clearance', true) IN ('PARTNER','ADMIN')
                        AND granted_by = current_setting('app.user_ref', true))
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS grant_admin ON document_grants")
    # Restore the 0008 flat form.
    op.execute("DROP POLICY IF EXISTS vault_a_clearance ON documents")
    op.execute("""
        CREATE POLICY vault_a_clearance ON documents
            AS RESTRICTIVE
            USING ((SELECT v.vault_type FROM vaults v WHERE v.id = vault_id) <> 'firm'
                OR classification_level IN ('PUBLIC','FIRM_INTERNAL')
                OR current_setting('app.user_clearance', true) IN ('PARTNER','ADMIN')
                OR EXISTS (SELECT 1 FROM document_grants g
                           WHERE g.document_id = documents.id
                             AND g.user_ref = current_setting('app.user_ref', true)))
            WITH CHECK (true)
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION vault_type_guard(p_document_id UUID)
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public
        AS $guard$
            SELECT EXISTS (
                SELECT 1 FROM documents d
                WHERE d.id = p_document_id
                  AND ((SELECT v.vault_type FROM vaults v WHERE v.id = d.vault_id) <> 'firm'
                       OR d.classification_level IN ('PUBLIC','FIRM_INTERNAL')
                       OR current_setting('app.user_clearance', true) IN ('PARTNER','ADMIN')
                       OR EXISTS (SELECT 1 FROM document_grants g
                                  WHERE g.document_id = d.id
                                    AND g.user_ref = current_setting('app.user_ref', true)))
            )
        $guard$
    """)
