"""Firm communication channels — Feature-Addendum §7 (Core tier).

DDL transcribed from docs/RedCase-Feature-Addendum.md §7 (source of truth).
Additions/adaptations, recorded per HANDOFF.md rule 3:
  * ``channels.matter_id`` ships WITHOUT the FK — matters is Phase 2 and
    does not exist yet (same conflict as 0003's document_analyses.matter_id;
    the FK lands with the Phase 2 matters migration). Column nullable.
  * §7's ``UNIQUE (tenant_id, matter_id, name)`` is kept verbatim. Caveat
    recorded: Postgres treats NULLs as distinct, so verbatim UNIQUE does
    NOT dedupe firm-wide channels (matter_id NULL). The provisioning
    function below uses ``IS NOT DISTINCT FROM`` for its own idempotency;
    enforcement for FIRM-kind duplicates is app-level until Phase 2.
  * §7 says nothing about RLS; both tables get tenant_isolation policies
    (USING + WITH CHECK) per convention 5.
  * ``provision_matter_channel`` implements the §7 auto-provision rule
    (Slack convention ``#case-{a}-v-{b}``) as a DB function so the Phase 2
    matters migration/endpoint can call it with a single statement.
    Phase 1 has no matters table, so nothing calls it yet — the function
    is the contract. It runs as the migration owner (RLS bypass) because
    provisioning is a system operation.
  * Seed: aetoes gets one firm-wide '#general' channel (§7: "an onboarded
    firm gets a communication/collaboration channel without depending on
    Slack"). Fixed UUID keeps tests deterministic.

ZDR: §7 rule kept — messages reference document_id/analysis_id, never
hold document content.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-17

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_AETOES = "a0000001-0000-4000-8000-000000000001"
GENERAL_CHANNEL = "c0000001-0000-4000-8000-000000000001"


def upgrade() -> None:
    # --- Channels — §7 verbatim except the matters FK (see header) ---
    op.execute("""
        CREATE TABLE channels (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID NOT NULL REFERENCES tenants(id),
            matter_id   UUID,                             -- FK deferred to Phase 2 (matters)
            name        TEXT NOT NULL,                    -- '#case-fbn-v-aetoes' or '#general'
            kind        TEXT NOT NULL DEFAULT 'MATTER'
                        CHECK (kind IN ('FIRM','MATTER','DIRECT')),
            created_at  TIMESTAMPTZ DEFAULT now(),
            UNIQUE (tenant_id, matter_id, name)
        )
    """)

    # --- Channel messages — §7 verbatim ---
    op.execute("""
        CREATE TABLE channel_messages (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID NOT NULL REFERENCES tenants(id),
            channel_id  UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            sender_ref  TEXT NOT NULL,
            body        TEXT NOT NULL,
            thread_id   UUID REFERENCES channel_messages(id),
            document_id UUID REFERENCES documents(id),        -- attachment reference
            analysis_id UUID REFERENCES document_analyses(id),-- shared battle card etc.
            created_at  TIMESTAMPTZ DEFAULT now()
        )
    """)

    # --- Matter-channel auto-provision (§7 Slack convention) ---
    # Phase 1 exposes the contract as a function; the Phase 2 matters
    # creation path calls it. IS NOT DISTINCT FROM matches NULL matter_id
    # correctly (the verbatim UNIQUE constraint cannot — see header).
    op.execute("""
        CREATE OR REPLACE FUNCTION provision_matter_channel(
            p_tenant_id UUID,
            p_matter_id UUID,
            p_claimant TEXT,
            p_defendant TEXT
        ) RETURNS UUID
        LANGUAGE plpgsql AS $$
        DECLARE
            v_name TEXT := '#case-'
                || btrim(lower(regexp_replace(p_claimant, '[^A-Za-z0-9]+', '-', 'g')), '-')
                || '-v-'
                || btrim(lower(regexp_replace(p_defendant, '[^A-Za-z0-9]+', '-', 'g')), '-');
            v_id UUID;
        BEGIN
            SELECT id INTO v_id FROM channels
             WHERE tenant_id = p_tenant_id
               AND matter_id IS NOT DISTINCT FROM p_matter_id
               AND name = v_name;
            IF v_id IS NULL THEN
                INSERT INTO channels (tenant_id, matter_id, name, kind)
                VALUES (p_tenant_id, p_matter_id, v_name, 'MATTER')
                RETURNING id INTO v_id;
            END IF;
            RETURN v_id;
        END $$
    """)

    # --- Row-Level Security (convention 5; see header) ---
    op.execute("ALTER TABLE channels ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE channel_messages ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON channels
            USING (tenant_id = current_setting('app.tenant_id')::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id')::UUID)
    """)
    op.execute("""
        CREATE POLICY tenant_isolation ON channel_messages
            USING (tenant_id = current_setting('app.tenant_id')::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id')::UUID)
    """)

    # --- Seed: tenant zero's firm-wide channel (see header) ---
    op.execute(f"""
        INSERT INTO channels (id, tenant_id, name, kind)
        VALUES ('{GENERAL_CHANNEL}', '{TENANT_AETOES}', '#general', 'FIRM')
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS provision_matter_channel(UUID, UUID, TEXT, TEXT)")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON channel_messages")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON channels")
    op.execute("ALTER TABLE channel_messages DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE channels DISABLE ROW LEVEL SECURITY")
    op.execute("DROP TABLE IF EXISTS channel_messages")
    op.execute("DROP TABLE IF EXISTS channels")
