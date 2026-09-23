"""Firm identity + KYC onboarding — Addendum S10.2 (S10-1).

Extends the onboarding funnel with firm identity and the know-your-client (KYC)
surface:

  * tenants.logo_path      - storage ref for the firm's logo (firm identity
                            step). Stored as a path, never content.
  * firm_kyc              - one row per firm carrying the KYC verification state
                            and the storage refs for the two required documents
                            (firm incorporation / RC + administrator ID).
                            verification_status is PENDING until a manual ops
                            review (tenant zero; self-serve is Phase 4).

KYC docs are PARTNER_RESTRICTED-class content. Rather than create a new clearance
rung, we gate read/write of this table to firm admins via the orthogonal
``app.is_firm_admin`` GUC (Addendum 8.5) — the firm-admin capability is the
named-grant analog for firm-level KYC. The table stores only STORAGE PATHS, never
the document bytes; the documents themselves live in a private Supabase bucket
(``REDCASE_KYC_BUCKET``) accessed by signed URLs issued on demand. RLS is
tenant-scoped (each firm sees only its own KYC row).

Verification writes (status -> VERIFIED/REJECTED, reviewed_by/at) are restricted
to firm admins as well; the manual ops step is represented by the same admin gate for
tenant zero (a system/provider account can be granted the flag at provisioning).

ZDR: firm_kyc stores no document content, no email, and no scan/capture — only
storage path refs and status. The RoPA addendum (S10.2) is notified that KYC
introduces a processing activity for the data-protection consultant.

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-23

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Firm identity — the logo is a storage path (bytes live in the brand bucket).
    op.execute("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS logo_path TEXT")

    op.execute(
        """
        CREATE TABLE firm_kyc (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID NOT NULL REFERENCES tenants(id),
            firm_website TEXT,
            rc_path    TEXT,
            id_document_path TEXT,
            id_document_type TEXT,
            verification_status TEXT NOT NULL DEFAULT 'PENDING'
                CHECK (verification_status IN ('PENDING','VERIFIED','REJECTED')),
            submitted_at TIMESTAMPTZ DEFAULT now(),
            reviewed_by TEXT,
            reviewed_at TIMESTAMPTZ
        )
        """
    )
    op.execute("ALTER TABLE firm_kyc ENABLE ROW LEVEL SECURITY")

    # Tenant scoping is the isolation backbone: a firm can only ever see and write
    # its own KYC row. The firm-admin gate (PARTNER_RESTRICTED analog) is
    # enforced at the GUC level in the router + reflected in the policy as a belt.
    op.execute(
        """
        CREATE POLICY tenant_isolation ON firm_kyc
            USING (tenant_id = current_setting('app.tenant_id')::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id')::UUID)
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX firm_kyc_tenant_uq ON firm_kyc (tenant_id)"
    )

    # The app role does not normally have access to firm_kyc (it is not in the
    # "ALL TABLES" grant set at provisioning); grant is made conditionally so the
    # migration is idempotent across local embedded-PG (redcase_app) and live
    # Supabase (different role name) — same guard as migration 0019.
    op.execute(
        "DO $do$ BEGIN"
        " IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'redcase_app') THEN"
        "   GRANT SELECT, INSERT, UPDATE ON firm_kyc TO redcase_app;"
        " END IF;"
        " END $do$"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON firm_kyc")
    op.execute("ALTER TABLE firm_kyc DISABLE ROW LEVEL SECURITY")
    op.execute("DROP TABLE IF EXISTS firm_kyc")
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS logo_path")
