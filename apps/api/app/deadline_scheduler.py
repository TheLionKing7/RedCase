"""Idempotent deadline notification sweep for the 07:00 Lagos job."""
from datetime import date
import uuid


async def sweep_deadline_notifications(conn, *, tenant_id: str, today: date) -> int:
    """Post each due lead notification once and mark its event notified.

    The row lock and unique idempotency key make retries safe across multiple
    scheduler invocations. Delivery is the existing in-app matter channel;
    external providers can consume the same durable notification ledger later.
    """
    rows = await conn.fetch(
        "SELECT n.id,n.event_id,n.channel_id,n.lead_days,e.description,e.due_date "
        "FROM deadline_notifications n JOIN deadline_events e ON e.id=n.event_id "
        "WHERE n.tenant_id=$1 AND n.sent_at IS NULL "
        "AND e.due_date IS NOT NULL AND e.due_date - $2::date <= n.lead_days "
        "AND e.status NOT IN ('DISMISSED','MISSED') FOR UPDATE OF n SKIP LOCKED",
        uuid.UUID(tenant_id), today,
    )
    sent = 0
    for row in rows:
        inserted = await conn.fetchrow(
            "INSERT INTO channel_messages (tenant_id,channel_id,sender_ref,sender_kind,body,idempotency_key) "
            "VALUES ($1,$2,'deadline-engine','SYSTEM',$3,$4) ON CONFLICT (tenant_id,idempotency_key) DO NOTHING RETURNING id",
            uuid.UUID(tenant_id), row["channel_id"],
            f"Deadline alert: {row['description']} — due {row['due_date'].isoformat()} (T-{row['lead_days']})",
            f"deadline-notification:{row['id']}",
        )
        await conn.execute(
            "UPDATE deadline_notifications SET sent_at=now() WHERE id=$1 AND sent_at IS NULL",
            row["id"],
        )
        await conn.execute(
            "UPDATE deadline_events SET status='NOTIFIED' WHERE id=$1 AND status='PENDING'",
            row["event_id"],
        )
        sent += 1 if inserted else 0
    return sent