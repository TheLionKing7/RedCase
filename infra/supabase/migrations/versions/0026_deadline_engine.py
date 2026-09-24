"""Deferred 0024 deadline-engine slice, promoted as the only next revision."""
from collections.abc import Sequence
from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
VALIDATED_AT = "2026-09-24 00:00:00+00"
VALIDATED_BY = "Tomiwa Akindoyin, Aetoes Legal"


def upgrade() -> None:
    op.execute("""
    CREATE TABLE deadline_rules (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(), jurisdiction TEXT NOT NULL DEFAULT 'NG',
      court_level TEXT NOT NULL, rule_name TEXT NOT NULL, trigger_event TEXT NOT NULL,
      rule_kind TEXT NOT NULL CHECK (rule_kind IN ('FIXED_DAYS','OPEN_ENDED')),
      offset_days INTEGER, computation TEXT NOT NULL,
      roll_over_enabled BOOLEAN NOT NULL DEFAULT FALSE, enabled BOOLEAN NOT NULL DEFAULT TRUE,
      validated_by TEXT NOT NULL, validated_at TIMESTAMPTZ NOT NULL, source_ref TEXT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      CHECK ((rule_kind = 'FIXED_DAYS' AND offset_days IS NOT NULL AND offset_days >= 0)
          OR (rule_kind = 'OPEN_ENDED' AND offset_days IS NULL)),
      UNIQUE (jurisdiction, court_level, rule_name)
    )
    """)
    op.execute("""
    CREATE TABLE deadline_events (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id UUID NOT NULL REFERENCES tenants(id),
      matter_id UUID NOT NULL REFERENCES matters(id), source_document_id UUID REFERENCES documents(id),
      rule_id UUID NOT NULL REFERENCES deadline_rules(id), event_type TEXT NOT NULL,
      alert_kind TEXT NOT NULL CHECK (alert_kind IN ('DEADLINE','WATCH')),
      description TEXT NOT NULL, trigger_date DATE NOT NULL, due_date DATE,
      confidence NUMERIC(3,2), status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING','NOTIFIED','DISMISSED','MISSED')),
      source_ref TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      CHECK ((alert_kind = 'DEADLINE' AND due_date IS NOT NULL) OR (alert_kind = 'WATCH' AND due_date IS NULL)),
      UNIQUE (tenant_id, matter_id, source_document_id, rule_id, trigger_date)
    )
    """)
    op.execute("""
    CREATE TABLE deadline_notifications (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id UUID NOT NULL REFERENCES tenants(id),
      event_id UUID NOT NULL REFERENCES deadline_events(id) ON DELETE CASCADE,
      channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE, lead_days INTEGER NOT NULL,
       sent_at TIMESTAMPTZ, UNIQUE (tenant_id, event_id, channel_id, lead_days)
    )
    """)
    op.execute("CREATE INDEX deadline_rules_lookup ON deadline_rules (court_level, trigger_event, enabled)")
    op.execute("CREATE INDEX deadline_events_tracker ON deadline_events (tenant_id, due_date, status)")
    op.execute("ALTER TABLE deadline_rules ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE deadline_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE deadline_notifications ENABLE ROW LEVEL SECURITY")
    for table in ("deadline_rules", "deadline_events", "deadline_notifications"):
        op.execute(f"CREATE POLICY tenant_isolation ON {table} USING (" \
                   f"{('true' if table == 'deadline_rules' else 'tenant_id = current_setting(\'app.tenant_id\')::UUID')})")
    op.execute(f"""
    INSERT INTO deadline_rules
      (jurisdiction,court_level,rule_name,trigger_event,rule_kind,offset_days,computation,validated_by,validated_at,source_ref)
    VALUES
      ('NG','COURT_OF_APPEAL','interlocutory_appeal','delivery/date of ruling','FIXED_DAYS',14,'CALENDAR_INCLUSIVE','{VALIDATED_BY}','{VALIDATED_AT}','docs/table-1790261132382.csv'),
      ('NG','COURT_OF_APPEAL','final_judgment_appeal','delivery/date of judgment','FIXED_DAYS',30,'CALENDAR_INCLUSIVE','{VALIDATED_BY}','{VALIDATED_AT}','docs/table-1790261132382.csv'),
      ('NG','STATE_HIGH_COURT','default_judgment_set_aside','delivery/date of judgment','FIXED_DAYS',14,'CALENDAR_INCLUSIVE','{VALIDATED_BY}','{VALIDATED_AT}','docs/table-1790261132382.csv; label: State High Court'),
      ('NG','ALL','computation_general','—','FIXED_DAYS',0,'CALENDAR_INCLUSIVE','{VALIDATED_BY}','{VALIDATED_AT}','docs/table-1790261132382.csv')
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS deadline_notifications")
    op.execute("DROP TABLE IF EXISTS deadline_events")
    op.execute("DROP TABLE IF EXISTS deadline_rules")
