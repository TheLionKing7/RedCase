"""Pure counsel-validated deadline calculations."""
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class DeadlineResult:
    due_date: date | None
    alert_kind: str
    reason: str | None = None


def _is_weekend(day: date) -> bool:
    return day.weekday() >= 5


def compute_deadline(
    trigger_date: date,
    *,
    rule_kind: str,
    offset_days: int | None,
    computation: str,
    roll_over: bool = False,
    holidays: frozenset[date] = frozenset(),
) -> DeadlineResult:
    """Compute a rule row without side effects."""
    if rule_kind == "OPEN_ENDED":
        return DeadlineResult(None, "WATCH", "reasonable time is open-ended")
    if rule_kind != "FIXED_DAYS" or offset_days is None or offset_days < 0:
        raise ValueError("fixed rules require a non-negative offset_days")
    if computation == "CALENDAR_INCLUSIVE" and offset_days <= 6:
        remaining = offset_days
        current = trigger_date
        while remaining:
            current += timedelta(days=1)
            if not (_is_weekend(current) or current in holidays):
                remaining -= 1
        due = current
    else:
        due = trigger_date + timedelta(days=offset_days)
    if roll_over:
        while _is_weekend(due) or due in holidays:
            due += timedelta(days=1)
    return DeadlineResult(due, "DEADLINE")
