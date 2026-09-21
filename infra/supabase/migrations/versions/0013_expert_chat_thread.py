"""Expert Chat thread link on query_audit (Addendum §3.1, Step D).

§3.1 reuses query_audit for chat messages — no new content table. The
``expert_chat_threads`` table itself was first created in 0003 (with RLS); Step A
added ``analysis_id``. This adds ``thread_id`` so an Expert Chat turn (the per-user
Legal Assistant, the only conversational surface) is an append-only audit row scoped to its
thread. Nullable: non-chat /v1/query traffic carries NULL.

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-21
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE query_audit"
        " ADD COLUMN thread_id UUID REFERENCES expert_chat_threads(id)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE query_audit DROP COLUMN IF EXISTS thread_id")

