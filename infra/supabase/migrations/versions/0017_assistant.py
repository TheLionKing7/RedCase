"""Legal Assistant — per-user conversational agent tables (Addendum §7.2, §3.1).

The ONE conversational agent, scoped per-user (one per licensed lawyer's Workbench,
premium entitlement ``workbench.assistant``). The assistant is a bounded ReAct agent
(planner -> executor -> verifier, max 6 tool iterations) whose available tools wrap
existing contracts: search_vault_a (grant-scoped), search_vault_b (grounded research
engine), analyze_document (existing analysis pipeline), matter_context (matters/deadline/
time summaries), save_to_workbench (draft/note artifacts).

Conversation model extension (recorded per HANDOFF.md rule 3): Addendum §3.1 reuses
query_audit for stateless Expert Chat turns (question stored as hash). The §7.2 Legal
Assistant is a persistent, per-user conversational surface whose "learns from the principal"
mechanisms need a system of record (user text + assistant replies persist), so we add explicit
conversation tables. ZDR unchanged: raw retrieved document text and LLM request payloads are
NEVER persisted; only user text, assistant reply, tool metadata (names + iteration counts),
and citation objects. Per-user isolation (DoD 3) is enforced in SQL (tenant + user
RESTRICTIVE policies), not only in Python.

Revision ID: 0017  Revises: 0016
Create Date: 2026-09-21
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE assistant_threads (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID NOT NULL REFERENCES tenants(id),
            created_by  TEXT NOT NULL,
            title       TEXT NOT NULL DEFAULT 'Untitled thread',
            created_at  TIMESTAMPTZ DEFAULT now(),
            updated_at  TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX assistant_threads_user_idx"
        " ON assistant_threads (tenant_id, created_by, updated_at DESC)"
    )
    op.execute(
        """
        CREATE TABLE assistant_messages (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id),
            thread_id      UUID NOT NULL REFERENCES assistant_threads(id) ON DELETE CASCADE,
            role           TEXT NOT NULL CHECK (role IN ('USER','ASSISTANT')),
            content        TEXT NOT NULL,
            question_hash  TEXT,
            citations     JSONB,
            tool_uses     JSONB,
            serving_provider TEXT,
            serving_model   TEXT,
            created_at    TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX assistant_messages_thread_idx"
        " ON assistant_messages (tenant_id, thread_id, created_at)"
    )
    op.execute(
        """
        CREATE TABLE assistant_preferences (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID NOT NULL REFERENCES tenants(id),
            user_ref   TEXT NOT NULL,
            pref_key   TEXT NOT NULL,
            pref_value JSONB NOT NULL,
            source     TEXT NOT NULL DEFAULT 'SETTING'
                       CHECK (source IN ('SETTING','CORRECTION','OBSERVED')),
            created_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX assistant_preferences_user_idx"
        " ON assistant_preferences (tenant_id, user_ref, pref_key)"
    )
    op.execute(
        """
        CREATE TABLE assistant_feedback (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id      UUID NOT NULL REFERENCES tenants(id),
            thread_id     UUID NOT NULL REFERENCES assistant_threads(id) ON DELETE CASCADE,
            message_id    UUID NOT NULL REFERENCES assistant_messages(id) ON DELETE CASCADE,
            user_ref      TEXT NOT NULL,
            rating        TEXT NOT NULL CHECK (rating IN ('UP','DOWN')),
            correction_text TEXT,
            created_at    TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX assistant_feedback_msg_idx"
        " ON assistant_feedback (tenant_id, thread_id, message_id)"
    )
    op.execute(
        """
        CREATE TABLE assistant_artifacts (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id  UUID NOT NULL REFERENCES tenants(id),
            thread_id UUID NOT NULL REFERENCES assistant_threads(id) ON DELETE CASCADE,
            created_by TEXT NOT NULL,
            kind      TEXT NOT NULL CHECK (kind IN ('DRAFT','NOTE')),
            title     TEXT NOT NULL,
            body      TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX assistant_artifacts_thread_idx
            ON assistant_artifacts (tenant_id, thread_id, created_at)
        """
    )
    # --- RLS: tenant + per-user isolation (DoD 3). Single PERMISSIVE policy per
    # table carrying BOTH conditions in USING and WITH CHECK, so tenant AND owner
    # must hold (the codebase's PERMISSIVE convention — RESTRICTIVE policies block
    # inserts for the app role even with WITH CHECK true, verified in dev).
    for path in (
        ("assistant_threads", "created_by", "created_by"),
        # assistant_artifacts: owner = created_by.
    ):
        table, user_col = path[0], path[1]
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_user_isolation ON {table}
                USING (tenant_id = current_setting('app.tenant_id')::UUID
                       AND {user_col} = current_setting('app.user_ref'))
                WITH CHECK (tenant_id = current_setting('app.tenant_id')::UUID
                          AND {user_col} = current_setting('app.user_ref'))
            """
        )

    # assistant_messages: no user_ref — derive owner through the thread.
    op.execute("ALTER TABLE assistant_messages ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_user_isolation ON assistant_messages
            USING (tenant_id = current_setting('app.tenant_id')::UUID
                   AND thread_id IN (
                       SELECT id FROM assistant_threads
                        WHERE created_by = current_setting('app.user_ref')
                   ))
            WITH CHECK (tenant_id = current_setting('app.tenant_id')::UUID
                       AND thread_id IN (
                           SELECT id FROM assistant_threads
                            WHERE created_by = current_setting('app.user_ref')
                       ))
        """
    )
    op.execute("ALTER TABLE assistant_artifacts ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_user_isolation ON assistant_artifacts
            USING (tenant_id = current_setting('app.tenant_id')::UUID
                   AND created_by = current_setting('app.user_ref'))
            WITH CHECK (tenant_id = current_setting('app.tenant_id')::UUID
                       AND created_by = current_setting('app.user_ref'))
        """
    )
    op.execute("ALTER TABLE assistant_preferences ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_user_isolation ON assistant_preferences
            USING (tenant_id = current_setting('app.tenant_id')::UUID
                   AND user_ref = current_setting('app.user_ref'))
            WITH CHECK (tenant_id = current_setting('app.tenant_id')::UUID
                       AND user_ref = current_setting('app.user_ref'))
        """
    )
    op.execute("ALTER TABLE assistant_feedback ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_user_isolation ON assistant_feedback
            USING (tenant_id = current_setting('app.tenant_id')::UUID
                   AND user_ref = current_setting('app.user_ref'))
            WITH CHECK (tenant_id = current_setting('app.tenant_id')::UUID
                       AND user_ref = current_setting('app.user_ref'))
        """
    )




def downgrade() -> None:
    for table in (
        "assistant_artifacts",
        "assistant_feedback",
        "assistant_preferences",
        "assistant_messages",
        "assistant_threads",
    ):
        op.execute(f"DROP POLICY IF EXISTS tenant_user_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")


