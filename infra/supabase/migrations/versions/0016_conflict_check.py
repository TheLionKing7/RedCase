"""Conflict check at client intake — Addendum §9.1, task 3.9 sub-task 3.

Three tiers of party-name matching (exact / fuzzy / phonetic) across the tenant's
own conflict surfaces — `clients`, `matters`, and Vault A `documents.case_title`
— producing a scored candidate list. Detection is advisory: the FIRM confirms or
dismisses each candidate; both the check and the decision are append-only audit rows.

Ownership & contract:
  * Every surface is tenant-scoped. The public corpus (Vault B) is deliberately
    NOT a conflict surface: a party appearing in a public judgment is not a conflict
    of interest, and including it would flood lawyers with noise (alarm fatigue).
  * `conflict_checks` — one row per screening request. It is the durable audit
    record of WHAT was screened, WHEN, and BY WHOM (created_by/user_ref).
  * `conflict_candidates` — one row per matched candidate: tier, source_kind
    (CLIENT|MATTER|VAULT_A), matched name, score, and the machine-readable
    reasons[] the matcher produced. A check with zero candidates simply has no rows.
  * `conflict_decisions` — the firm's CONFIRMED/DISMISSED ruling. A SEPARATE
    append-only row (never mutated in place) so the audit trail records both the
    detection and the human verdict, in that order, immutably.
  * RLS (HANDOFF §2.5): tenant_isolation policies on all three tables, same
    shape as the rest of the chain (migration 0002 precedent). FK-driven
    cross-table access in the decision path is validated for tenancy in the router.

The candidate list is tuned toward RECALL with explicit match reasons and a floor,
per the alarm-fatality brief: the firm's one-click confirm/dismiss is cheap, so a
few extra plausible (non-flooding) candidates are acceptable; a false NEGATIVE is not.
"""

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE conflict_checks (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID NOT NULL REFERENCES tenants(id),
            party_name  TEXT NOT NULL,
            source     TEXT NOT NULL DEFAULT 'INTAKE'
                        CHECK (source IN ('INTAKE','MATTER','MANUAL')),
            created_by  TEXT NOT NULL,
            created_at  TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE conflict_candidates (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            check_id     UUID NOT NULL REFERENCES conflict_checks(id) ON DELETE CASCADE,
            tenant_id    UUID NOT NULL REFERENCES tenants(id),
            tier        TEXT NOT NULL
                            CHECK (tier IN ('EXACT','FUZZY','PHONETIC')),
            source_kind TEXT NOT NULL
                            CHECK (source_kind IN ('CLIENT','MATTER','VAULT_A')),
            source_id   UUID NOT NULL,
            matched_name TEXT NOT NULL,
            score      NUMERIC(5,4) NOT NULL,
            reasons    JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at  TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_conflict_candidates_check ON conflict_candidates (check_id)
        """
    )
    op.execute(
        """
        CREATE TABLE conflict_decisions (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            check_id    UUID NOT NULL REFERENCES conflict_checks(id) ON DELETE CASCADE,
            tenant_id   UUID NOT NULL REFERENCES tenants(id),
            decision    TEXT NOT NULL CHECK (decision IN ('CONFIRMED','DISMISSED')),
            decided_by  TEXT NOT NULL,
            decided_at  TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        """
        ALTER TABLE conflict_checks ENABLE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        ALTER TABLE conflict_candidates ENABLE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        ALTER TABLE conflict_decisions ENABLE ROW LEVEL SECURITY
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_isolation ON conflict_checks
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_isolation ON conflict_candidates
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_isolation ON conflict_decisions
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
        """
    )


def downgrade() -> None:
    for table in ("conflict_decisions", "conflict_candidates", "conflict_checks"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP TABLE IF EXISTS conflict_decisions")
    op.execute("DROP TABLE IF EXISTS conflict_candidates")
    op.execute("DROP TABLE IF EXISTS conflict_checks")
