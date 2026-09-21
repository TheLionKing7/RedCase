"""Agent participation in channel RLS (Addendum §7.2).

Extends can_read_channel (0011) to recognize AGENT participants, so a
functional agent registered in channel_participants (participant_kind='AGENT')
can POST to its channels through the same RLS predicate as a user. USER read
isolation is unchanged: user_refs are Supabase sub UUIDs and agent refs are
function labels ('red-teamer', 'deadline-tracker'), so the two never collide —
the predicate keys on participant_ref, not participant_kind.

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-21
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
                             AND cp.participant_ref = current_setting('app.user_ref', true)))
            )
        $guard$
    """)


def downgrade() -> None:
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
