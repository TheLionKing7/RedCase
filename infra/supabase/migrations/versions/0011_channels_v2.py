"""In-app channels v2 — participants, sender_kind, idempotency, per-participant RLS (Addendum §7.1).

Extends migration 0005 (channels + channel_messages + provision_matter_channel)
to the full §7.1 model. 0005 shipped the Phase-1 contract early (before the
Phase 2 matters table existed); this migration adds the remaining §7.1 surface
WITHOUT editing 0005 (linear chain — HANDOFF rule):

  * channel_messages.sender_kind (USER/AGENT/SYSTEM) — the agent-post label
    (task 2.6) and share-to-channel attribution both need it. DEFAULT 'USER'
    keeps 0005-era inserts valid.
  * channel_messages.idempotency_key — clients retry at-least-once; a unique
    index on (tenant_id, idempotency_key) collapses duplicates to one message.
    DEVIATION from §7.1's verbatim `idempotency_key TEXT UNIQUE` (global):
    a global unique would let one tenant's key collide with another's (DoS +
    cross-tenant read risk). Scoped to tenant per HANDOFF convention 5.
  * channel_participants — the membership table (USER or AGENT). §7.1 verbatim.
  * Per-participant READ isolation as RESTRICTIVE policies (the privilege
    layer): MATTER/DIRECT channels are readable only by their participants;
    FIRM channels (#general) stay tenant-wide. A non-participant reads ZERO
    rows at SQL level — the DoD. SEND is likewise participant-restricted for
    MATTER/DIRECT (RESTRICTIVE WITH CHECK). can_read_channel() is SECURITY
    DEFINER so the policy can see the membership table without self-reference.
  * provision_general_channel(p_tenant_id) — idempotent #general on onboarding.
  * provision_direct_channel(p_tenant_id, a, b) — idempotent DIRECT channel
    with both participants (sorted refs for determinism).

ZDR: messages reference documents/analyses by id; they never hold content.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-20
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- channel_messages gains sender_kind + idempotency_key (§7.1) ---
    op.execute("""
        ALTER TABLE channel_messages
            ADD COLUMN sender_kind TEXT NOT NULL DEFAULT 'USER'
                CHECK (sender_kind IN ('USER','AGENT','SYSTEM')),
            ADD COLUMN idempotency_key TEXT
    """)
    # Tenant-scoped idempotency (see header deviation).
    op.execute("""
        CREATE UNIQUE INDEX channel_messages_idempotency_key
            ON channel_messages (tenant_id, idempotency_key)
    """)

    # --- channel_participants (§7.1 verbatim) ---
    op.execute("""
        CREATE TABLE channel_participants (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID NOT NULL REFERENCES tenants(id),
            channel_id  UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            participant_ref TEXT NOT NULL,
            participant_kind TEXT NOT NULL CHECK (participant_kind IN ('USER','AGENT')),
            joined_at   TIMESTAMPTZ DEFAULT now(),
            UNIQUE (channel_id, participant_ref)
        )
    """)
    op.execute("ALTER TABLE channel_participants ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON channel_participants
            USING (tenant_id = current_setting('app.tenant_id')::UUID)
            WITH CHECK (tenant_id = current_setting('app.tenant_id')::UUID)
    """)

    # --- can_read_channel: the single privilege predicate ---
    # SECURITY DEFINER so the policy can read channels + channel_participants
    # without self-reference (same pattern as 0009's vault_type_guard).
    op.execute("""
        CREATE OR REPLACE FUNCTION can_read_channel(p_channel_id UUID)
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public
        AS $guard$
            SELECT EXISTS (
                SELECT 1 FROM channels c
                WHERE c.id = p_channel_id
                  AND (c.kind = 'FIRM'
                       OR EXISTS (
                           SELECT 1 FROM channel_participants cp
                           WHERE cp.channel_id = c.id
                             AND cp.participant_ref = current_setting('app.user_ref', true)
                             AND cp.participant_kind = 'USER'))
            )
        $guard$
    """)

    # --- channel_name: SECURITY DEFINER metadata read for provisioning/tests ---
    # A caller who just provisioned a MATTER/DIRECT channel is not yet a
    # participant, so a plain SELECT is blocked by participant_read. System
    # metadata reads (naming verification) need the same bypass as provisioning.
    op.execute("""
        CREATE OR REPLACE FUNCTION channel_name(p_channel_id UUID) RETURNS TEXT
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public
        AS $fn$
            SELECT name FROM channels WHERE id = p_channel_id
        $fn$
    """)

    # --- Re-create provision_matter_channel as SECURITY DEFINER ---
    # 0005 created it without SECURITY DEFINER, which was harmless while
    # channels had only tenant_isolation. With per-participant read RLS, the
    # function's idempotency SELECT can no longer see a MATTER channel it is
    # about to (re)create, so it would duplicate. System provisioning must
    # bypass RLS — same contract as 0005's header, now actually enforced.
    op.execute("""
        CREATE OR REPLACE FUNCTION provision_matter_channel(
            p_tenant_id UUID,
            p_matter_id UUID,
            p_claimant TEXT,
            p_defendant TEXT
        ) RETURNS UUID
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = public
        AS $$
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

    # --- Per-participant read isolation (RESTRICTIVE privilege layer) ---
    op.execute("""
        CREATE POLICY participant_read ON channels
            AS RESTRICTIVE
            USING (can_read_channel(id))
    """)
    op.execute("""
        CREATE POLICY participant_read ON channel_messages
            AS RESTRICTIVE
            USING (can_read_channel(channel_id))
    """)
    # --- Per-participant send (RESTRICTIVE WITH CHECK) ---
    op.execute("""
        CREATE POLICY participant_send ON channel_messages
            AS RESTRICTIVE
            WITH CHECK (can_read_channel(channel_id))
    """)

    # --- #general provisioning (idempotent, for tenant onboarding) ---
    # SECURITY DEFINER: provisioning is a system operation — it must see and
    # create channels regardless of the caller's (absent) participation.
    op.execute("""
        CREATE OR REPLACE FUNCTION provision_general_channel(p_tenant_id UUID)
        RETURNS UUID
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = public
        AS $$
        DECLARE
            v_id UUID;
        BEGIN
            SELECT id INTO v_id FROM channels
             WHERE tenant_id = p_tenant_id AND kind = 'FIRM' AND name = '#general';
            IF v_id IS NULL THEN
                INSERT INTO channels (tenant_id, name, kind)
                VALUES (p_tenant_id, '#general', 'FIRM')
                RETURNING id INTO v_id;
            END IF;
            RETURN v_id;
        END $$
    """)

    # --- DIRECT channel provisioning (idempotent, both participants) ---
    op.execute("""
        CREATE OR REPLACE FUNCTION provision_direct_channel(
            p_tenant_id UUID,
            p_user_a TEXT,
            p_user_b TEXT
        ) RETURNS UUID
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = public
        AS $$
        DECLARE
            v_lo TEXT := LEAST(p_user_a, p_user_b);
            v_hi TEXT := GREATEST(p_user_a, p_user_b);
            v_id UUID;
        BEGIN
            SELECT c.id INTO v_id
              FROM channels c
              JOIN channel_participants pa
                ON pa.channel_id = c.id AND pa.participant_ref = v_lo
              JOIN channel_participants pb
                ON pb.channel_id = c.id AND pb.participant_ref = v_hi
             WHERE c.tenant_id = p_tenant_id AND c.kind = 'DIRECT'
             LIMIT 1;
            IF v_id IS NULL THEN
                INSERT INTO channels (tenant_id, name, kind)
                VALUES (p_tenant_id, '#dm-' || v_lo || '-' || v_hi, 'DIRECT')
                RETURNING id INTO v_id;
                INSERT INTO channel_participants
                    (tenant_id, channel_id, participant_ref, participant_kind)
                VALUES (p_tenant_id, v_id, v_lo, 'USER'),
                       (p_tenant_id, v_id, v_hi, 'USER');
            END IF;
            RETURN v_id;
        END $$
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS provision_direct_channel(UUID, TEXT, TEXT)")
    op.execute("DROP FUNCTION IF EXISTS provision_general_channel(UUID)")
    op.execute("DROP FUNCTION IF EXISTS channel_name(UUID)")
    op.execute("DROP FUNCTION IF EXISTS can_read_channel(UUID)")
    op.execute("DROP POLICY IF EXISTS participant_send ON channel_messages")
    op.execute("DROP POLICY IF EXISTS participant_read ON channel_messages")
    op.execute("DROP POLICY IF EXISTS participant_read ON channels")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON channel_participants")
    op.execute("ALTER TABLE channel_participants DISABLE ROW LEVEL SECURITY")
    op.execute("DROP TABLE IF EXISTS channel_participants")
    op.execute("DROP INDEX IF EXISTS channel_messages_idempotency_key")
    op.execute("""
        ALTER TABLE channel_messages
            DROP COLUMN IF EXISTS idempotency_key,
            DROP COLUMN IF EXISTS sender_kind
    """)

