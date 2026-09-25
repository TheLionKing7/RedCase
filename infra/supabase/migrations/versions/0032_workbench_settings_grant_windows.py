"""Workbench preferences, editable profile contact fields, and grant windows."""

from collections.abc import Sequence

from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE agent_personas ADD COLUMN personality TEXT")
    op.execute("ALTER TABLE agent_personas ADD COLUMN working_style TEXT")
    op.execute("ALTER TABLE agent_personas ADD COLUMN reviewer_specialty TEXT")
    op.execute("ALTER TABLE agent_personas ADD COLUMN researcher_specialty TEXT")
    op.execute("ALTER TABLE agent_personas ADD COLUMN redteam_temperature NUMERIC(3,2) NOT NULL DEFAULT 0.20 CHECK (redteam_temperature BETWEEN 0 AND 1)")

    op.execute("ALTER TABLE firm_members ADD COLUMN phone TEXT")
    op.execute("ALTER TABLE firm_members ADD COLUMN email TEXT")
    op.execute("ALTER TABLE firm_members ADD COLUMN timezone TEXT NOT NULL DEFAULT 'Africa/Lagos'")

    op.execute("ALTER TABLE document_grants ADD COLUMN expires_at TIMESTAMPTZ")
    op.execute("ALTER TABLE document_grants ADD COLUMN relinquished_at TIMESTAMPTZ")
    op.execute("ALTER TABLE access_requests ADD COLUMN requested_title TEXT")
    op.execute("ALTER TABLE access_requests ALTER COLUMN document_id DROP NOT NULL")
    op.execute("ALTER TABLE document_grants DROP CONSTRAINT IF EXISTS document_grants_document_id_user_ref_key")
    op.execute("CREATE INDEX document_grants_active_user_idx ON document_grants (tenant_id, user_ref, granted_at DESC) WHERE relinquished_at IS NULL")
    # Both document rows and retrieval chunks use the same active-grant rule.
    op.execute("DROP POLICY IF EXISTS vault_a_clearance ON documents")
    op.execute("""
        CREATE POLICY vault_a_clearance ON documents
            AS RESTRICTIVE
            USING ((SELECT v.vault_type FROM vaults v WHERE v.id = vault_id) <> 'firm'
                OR classification_level IN ('PUBLIC','FIRM_INTERNAL')
                OR (classification_level = 'CONFIDENTIAL'
                    AND current_setting('app.user_clearance', true) IN ('SENIOR','PARTNER','ADMIN'))
                OR EXISTS (SELECT 1 FROM document_grants g
                           WHERE g.document_id = documents.id
                             AND g.user_ref = current_setting('app.user_ref', true)
                             AND g.relinquished_at IS NULL
                             AND (g.expires_at IS NULL OR g.expires_at > now())))
            WITH CHECK (true)
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION vault_type_guard(p_document_id UUID)
        RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
        AS $guard$
            SELECT EXISTS (
                SELECT 1 FROM documents d
                WHERE d.id = p_document_id
                  AND ((SELECT v.vault_type FROM vaults v WHERE v.id = d.vault_id) <> 'firm'
                       OR d.classification_level IN ('PUBLIC','FIRM_INTERNAL')
                       OR (d.classification_level = 'CONFIDENTIAL'
                           AND current_setting('app.user_clearance', true) IN ('SENIOR','PARTNER','ADMIN'))
                       OR EXISTS (SELECT 1 FROM document_grants g
                                  WHERE g.document_id = d.id
                                    AND g.user_ref = current_setting('app.user_ref', true)
                                    AND g.relinquished_at IS NULL
                                    AND (g.expires_at IS NULL OR g.expires_at > now())))
            )
        $guard$
    """)

    # Grant-creation remains restricted to partner/admin. User-initiated
    # relinquishment is exposed only through the narrowly-scoped function below.
    op.execute("DROP POLICY IF EXISTS grant_admin ON document_grants")
    op.execute("""
        CREATE POLICY grant_admin ON document_grants AS RESTRICTIVE
        USING (true)
        WITH CHECK (current_setting('app.user_clearance', true) IN ('PARTNER','ADMIN')
                    AND granted_by = current_setting('app.user_ref', true))
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION relinquish_document_grant(p_grant_id UUID)
        RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
        AS $relinquish$
        DECLARE changed integer;
        BEGIN
            UPDATE document_grants
               SET relinquished_at = now()
             WHERE id = p_grant_id
               AND tenant_id = current_setting('app.tenant_id', true)::uuid
               AND user_ref = current_setting('app.user_ref', true)
               AND relinquished_at IS NULL;
            GET DIAGNOSTICS changed = ROW_COUNT;
            RETURN changed = 1;
        END
        $relinquish$
    """)
    op.execute("REVOKE ALL ON FUNCTION relinquish_document_grant(UUID) FROM PUBLIC")
    op.execute("""
        DO $do$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'redcase_app') THEN
            GRANT EXECUTE ON FUNCTION relinquish_document_grant(UUID) TO redcase_app;
          END IF;
        END $do$
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS relinquish_document_grant(UUID)")
    op.execute("ALTER TABLE access_requests ALTER COLUMN document_id SET NOT NULL")
    op.execute("ALTER TABLE access_requests DROP COLUMN IF EXISTS requested_title")
    op.execute("DROP INDEX IF EXISTS document_grants_active_user_idx")
    op.execute("ALTER TABLE document_grants ADD CONSTRAINT document_grants_document_id_user_ref_key UNIQUE (document_id, user_ref)")
    op.execute("ALTER TABLE document_grants DROP COLUMN IF EXISTS relinquished_at")
    op.execute("ALTER TABLE document_grants DROP COLUMN IF EXISTS expires_at")
    op.execute("ALTER TABLE firm_members DROP COLUMN IF EXISTS timezone")
    op.execute("ALTER TABLE firm_members DROP COLUMN IF EXISTS email")
    op.execute("ALTER TABLE firm_members DROP COLUMN IF EXISTS phone")
    op.execute("ALTER TABLE agent_personas DROP COLUMN IF EXISTS redteam_temperature")
    op.execute("ALTER TABLE agent_personas DROP COLUMN IF EXISTS researcher_specialty")
    op.execute("ALTER TABLE agent_personas DROP COLUMN IF EXISTS reviewer_specialty")
    op.execute("ALTER TABLE agent_personas DROP COLUMN IF EXISTS working_style")
    op.execute("ALTER TABLE agent_personas DROP COLUMN IF EXISTS personality")
    # Recreate the prior active-grant-independent predicate only after fields are removed.
    op.execute("DROP POLICY IF EXISTS vault_a_clearance ON documents")
    op.execute("""
        CREATE POLICY vault_a_clearance ON documents AS RESTRICTIVE
        USING ((SELECT v.vault_type FROM vaults v WHERE v.id = vault_id) <> 'firm'
            OR classification_level IN ('PUBLIC','FIRM_INTERNAL')
            OR (classification_level = 'CONFIDENTIAL'
                AND current_setting('app.user_clearance', true) IN ('SENIOR','PARTNER','ADMIN'))
            OR EXISTS (SELECT 1 FROM document_grants g WHERE g.document_id = documents.id
                       AND g.user_ref = current_setting('app.user_ref', true)))
        WITH CHECK (true)
    """)