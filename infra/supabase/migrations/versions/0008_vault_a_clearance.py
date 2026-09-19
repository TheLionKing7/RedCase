"""Vault A schema — clients, matters, document_grants, clearance RLS (Phase 2 §1.2).

Task 2.1 of the Phase 2 brief (owner 2026-09-19). DDL transcribed from
docs/RedCase-Phase2-Design.md §1.2 (source of truth). Deviations from the
doc, recorded per HANDOFF.md rule 3:

1. §1.2's policies reference ``documents.vault_type``, which does not exist
   — Phase 1's documents table scopes via ``vault_id -> vaults.vault_type``
   (the §1.2 ALTER list adds no such column). Minimal correction preserving
   the doc's intent verbatim-in-spirit: the vault-type test is written as
   the subquery ``(SELECT v.vault_type FROM vaults v WHERE v.id = vault_id)
   <> 'firm'`` in both the documents policy and the chunk guard function.
2. ``vault_type_guard()`` is specified with no arguments, but a policy
   function cannot see the row under evaluation — the doc's own comment
   says the guard "joins documents", which requires the chunk's
   document_id as a parameter. Implemented as
   ``vault_type_guard(p_document_id UUID)`` with the policy calling
   ``vault_type_guard(document_id)`` (the column resolves from the policy's
   row context). Name and semantics per the doc; signature is the minimal
   change that lets it exist at all.
3. §1.2's DDL creates clients/matters/document_grants WITHOUT tenant RLS
   policies. HANDOFF.md 2.5 (tenant scoping) is a non-negotiable convention
   in every file, and migration 0002 set the precedent for adding the
   policy a design doc omitted: tenant_isolation policies on all three new
   tables, same shape as the rest of the chain.
4. slack_intake is part of §1.2's DDL but NOT of the Task 2.1 brief
   (clients, matters, document_grants, clearance RLS); it belongs with the
   Slack binding work. Deferred deliberately, noted here.

7. The doc's grant EXISTS is written ``g.document_id = id`` — inside
   the subquery, unqualified ``id`` resolves to ``g.id`` (document_grants'
   own primary key), making the grant branch permanently false. Qualified
   as ``g.document_id = documents.id``. (The guard function was written
   with the alias qualified from the start; only the inline policy copied
   the doc's literal form.)

6. Both new policies are created AS RESTRICTIVE. The doc writes bare
   CREATE POLICY, which defaults to PERMISSIVE — and permissive policies
   OR together: Phase 1's tenant_isolation (permissive) would make every
   same-tenant row visible regardless of clearance, and the doc's own
   DoD ("Staff queries a PARTNER_RESTRICTED doc -> zero results in SQL")
   would be unmeetable. RESTRICTIVE policies AND with the permissive
   set: tenant isolation (OR group) x clearance (AND group) — the
   doc's stated intent ("Phase 1's tenant isolation stays; Phase 2 adds
   the privilege layer"). Caught by the Task 2.1 clearance battery
   before any deploy, which is the battery's job.

5. The doc writes single-argument current_setting() for the two new
   GUCs. Single-arg raises UndefinedObjectError when the placeholder is
   missing — and because OR-branch evaluation order is not guaranteed,
   EVERY pre-existing Phase 1 query path (retrieval over Vault B, the
   sweep, ingestion, the analyses worker) would start erroring the moment
   this migration lands, even though Vault B rows are classification-
   blind. Implemented with the missing-ok form current_setting(name,
   true): an unset GUC yields NULL -> condition false -> firm documents
   above FIRM_INTERNAL are DENIED (fail-closed by denial, the same
   security posture as Phase 1's error, without breaking Vault B).
   The Phase 2 request path still sets both GUCs per user per request.

Clearance contract: the request path sets app.tenant_id + app.user_ref
today (app/deps.py); Phase 2 adds app.user_clearance per request. Both
new GUCs have NO default — an unset app.user_clearance fails closed, the
established Phase 1 pattern. SENIOR sees FIRM_INTERNAL + grants only per
the doc's verbatim policy (the doc's prose implies an ordering
PARTNER > SENIOR > STAFF that the SQL does not encode — flagged to the
owner rather than silently extended).

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-19

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Clients & matters (firm-side scoping entities) — §1.2 verbatim ---
    op.execute("""
        CREATE TABLE clients (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID NOT NULL REFERENCES tenants(id),
            name        TEXT NOT NULL,
            contact_ref JSONB,
            created_at  TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE matters (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id    UUID NOT NULL REFERENCES tenants(id),
            client_id    UUID NOT NULL REFERENCES clients(id),
            matter_ref   TEXT NOT NULL,
            status       TEXT NOT NULL DEFAULT 'ACTIVE'
                         CHECK (status IN ('ACTIVE','CONCLUDED','ARCHIVED')),
            slack_channel TEXT UNIQUE,
            opened_at    TIMESTAMPTZ DEFAULT now(),
            UNIQUE (tenant_id, matter_ref)
        )
    """)

    # --- Vault A metadata extensions on documents — §1.2 verbatim ---
    op.execute("""
        ALTER TABLE documents ADD COLUMN client_id UUID REFERENCES clients(id)
    """)
    op.execute("""
        ALTER TABLE documents ADD COLUMN matter_id UUID REFERENCES matters(id)
    """)
    op.execute("""
        ALTER TABLE documents ADD COLUMN classification_level TEXT
            NOT NULL DEFAULT 'FIRM_INTERNAL'
            CHECK (classification_level IN
                   ('PUBLIC','FIRM_INTERNAL','CONFIDENTIAL','PARTNER_RESTRICTED'))
    """)
    op.execute("""
        ALTER TABLE documents ADD COLUMN encrypted_content_hash TEXT
    """)
    op.execute("""
        ALTER TABLE documents ADD COLUMN dek_wrapped BYTEA
    """)
    op.execute("""
        ALTER TABLE documents ADD COLUMN doc_type TEXT
            CHECK (doc_type IN
                   ('BRIEF','PLEADING','OPINION','CONTRACT','CORRESPONDENCE','OTHER'))
    """)

    # --- Document-level ACL: the privilege-isolation backbone — §1.2 verbatim ---
    op.execute("""
        CREATE TABLE document_grants (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID NOT NULL REFERENCES tenants(id),
            document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            user_ref    TEXT NOT NULL,
            grant_level TEXT NOT NULL DEFAULT 'READ'
                        CHECK (grant_level IN ('READ','ANNOTATE','ADMIN')),
            granted_by  TEXT NOT NULL,
            granted_at  TIMESTAMPTZ DEFAULT now(),
            UNIQUE (document_id, user_ref)
        )
    """)

    # --- Tenant isolation on the new tables (HANDOFF.md 2.5; see note 3) ---
    for table in ("clients", "matters", "document_grants"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY tenant_isolation ON {table}
                USING (tenant_id = current_setting('app.tenant_id')::UUID)
        """)

    # --- Privilege layer on documents — §1.2 verbatim modulo note 1 ---
    # Permissive policy: ORs with Phase 1's tenant_isolation. Non-firm
    # documents (Vault B juris) are unaffected by classification.
    op.execute("""
        CREATE POLICY vault_a_clearance ON documents
            AS RESTRICTIVE
            USING ((SELECT v.vault_type FROM vaults v WHERE v.id = vault_id) <> 'firm'
                OR classification_level = 'FIRM_INTERNAL'
                OR current_setting('app.user_clearance', true) IN ('PARTNER','ADMIN')
                OR EXISTS (SELECT 1 FROM document_grants g
                           WHERE g.document_id = documents.id
                             AND g.user_ref = current_setting('app.user_ref', true)))
    """)

    # --- Retrieval-time grant filter on chunks — §1.2 verbatim modulo notes 1-2 ---
    # SECURITY DEFINER: the guard must see ALL documents to evaluate the
    # policy (the caller's own RLS would make the inner EXISTS fail-closed
    # or self-referential). Owner = table owner bypasses RLS; the row pin
    # (d.id = p_document_id, FK-joined from the chunk) keeps it scoped.
    # SET search_path closes the usual SECURITY DEFINER hole.
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
                       OR d.classification_level = 'FIRM_INTERNAL'
                       OR current_setting('app.user_clearance', true) IN ('PARTNER','ADMIN')
                       OR EXISTS (SELECT 1 FROM document_grants g
                                  WHERE g.document_id = d.id
                                    AND g.user_ref = current_setting('app.user_ref', true)))
            )
        $guard$
    """)
    op.execute("""
        CREATE POLICY chunk_privilege ON document_chunks
            AS RESTRICTIVE
            USING (vault_type_guard(document_id))
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS chunk_privilege ON document_chunks")
    op.execute("DROP FUNCTION IF EXISTS vault_type_guard(UUID)")
    op.execute("DROP POLICY IF EXISTS vault_a_clearance ON documents")
    for table in ("document_grants", "matters", "clients"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP TABLE IF EXISTS document_grants")
    op.execute("""
        ALTER TABLE documents
            DROP COLUMN IF EXISTS doc_type,
            DROP COLUMN IF EXISTS dek_wrapped,
            DROP COLUMN IF EXISTS encrypted_content_hash,
            DROP COLUMN IF EXISTS classification_level,
            DROP COLUMN IF EXISTS matter_id,
            DROP COLUMN IF EXISTS client_id
    """)
    op.execute("DROP TABLE IF EXISTS matters")
    op.execute("DROP TABLE IF EXISTS clients")
