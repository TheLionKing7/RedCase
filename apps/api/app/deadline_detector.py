"""Metadata-only deadline detection and notification fan-out."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date

from app.deadline_engine import compute_deadline

DATE = r"(\d{4}-\d{2}-\d{2})"
PATTERNS = (
    ("delivery/date of ruling", re.compile(r"(?:ruling|decision)\D{0,30}" + DATE, re.I)),
    ("delivery/date of judgment", re.compile(r"(?:judgment|judgement)\D{0,30}" + DATE, re.I)),
)


@dataclass(frozen=True)
class DetectedDate:
    event: str
    trigger_date: date


def extract_delivery_dates(text: str) -> tuple[DetectedDate, ...]:
    """Extract only explicit ISO dates following ruling/judgment language."""
    found: list[DetectedDate] = []
    for event, pattern in PATTERNS:
        for match in pattern.finditer(text):
            found.append(DetectedDate(event, date.fromisoformat(match.group(1))))
    return tuple(dict.fromkeys(found))


async def detect_deadlines(conn, *, tenant_id: str, document_id: str, text: str) -> int:
    row = await conn.fetchrow(
        "SELECT matter_id, court_level FROM documents WHERE id = $1::uuid",
        uuid.UUID(document_id),
    )
    if not row or not row["matter_id"]:
        return 0
    created = 0
    for detected in extract_delivery_dates(text):
        rule = await conn.fetchrow(
            "SELECT * FROM deadline_rules WHERE enabled AND court_level = $1 "
            "AND trigger_event = $2 ORDER BY id LIMIT 1",
            row["court_level"], detected.event,
        )
        if not rule:
            continue
        result = compute_deadline(detected.trigger_date, rule_kind=rule["rule_kind"],
            offset_days=rule["offset_days"], computation=rule["computation"])
        event = await conn.fetchrow(
            "INSERT INTO deadline_events (tenant_id,matter_id,source_document_id,rule_id,event_type,alert_kind,description,trigger_date,due_date,source_ref) "
            "VALUES ($1,$2,$3,$4,'FILING_DEADLINE',$5,$6,$7,$8,$9) ON CONFLICT DO NOTHING RETURNING id",
            uuid.UUID(tenant_id), row["matter_id"], uuid.UUID(document_id), rule["id"], result.alert_kind,
            rule["rule_name"], detected.trigger_date, result.due_date, rule["source_ref"],
        )
        if event:
            created += 1
            await conn.execute("INSERT INTO deadline_notifications (tenant_id,event_id,channel_id,lead_days) "
                "SELECT $1,$2,c.id,v.lead FROM channels c CROSS JOIN (VALUES (7),(2),(0)) v(lead) "
                "WHERE c.tenant_id=$1 AND c.matter_id=$3 ON CONFLICT DO NOTHING",
                uuid.UUID(tenant_id), event["id"], row["matter_id"])
    return created