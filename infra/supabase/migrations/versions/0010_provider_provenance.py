"""Answer-provider provenance on query_audit (Task 2.6 provider fallback chain).

The runtime fallback chain (make_llm) can serve an answer from a different
provider than ANSWER_MODEL_PRIMARY when the primary 429s persistently or
hard-fails (402 exhausted quota). Recording the ACTUAL serving provider per
answer row keeps the audit trail self-describing — without it, a future
calibration reader would see DeepSeek-attributed latencies on a run configured
for explabs and conclude the pipeline regressed.

Columns are nullable: threshold-only refusals and routing rows never reach an
answer LLM and carry NULL serving_provider/serving_model.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-20
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE query_audit ADD COLUMN serving_provider TEXT")
    op.execute("ALTER TABLE query_audit ADD COLUMN serving_model TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE query_audit DROP COLUMN IF EXISTS serving_model")
    op.execute("ALTER TABLE query_audit DROP COLUMN IF EXISTS serving_provider")
