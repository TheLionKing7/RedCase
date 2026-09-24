from datetime import date

from app.deadline_engine import compute_deadline


def test_march_17_worked_example():
    result = compute_deadline(date(2026, 3, 3), rule_kind="FIXED_DAYS", offset_days=14, computation="CALENDAR_INCLUSIVE")
    assert result.due_date == date(2026, 3, 17)
    assert result.alert_kind == "DEADLINE"


def test_day_after_is_day_one():
    result = compute_deadline(date(2026, 3, 2), rule_kind="FIXED_DAYS", offset_days=1, computation="CALENDAR_INCLUSIVE")
    assert result.due_date == date(2026, 3, 3)


def test_short_period_excludes_weekends_and_holidays():
    result = compute_deadline(date(2026, 3, 6), rule_kind="FIXED_DAYS", offset_days=2, computation="CALENDAR_INCLUSIVE", holidays=frozenset({date(2026, 3, 10)}))
    assert result.due_date == date(2026, 3, 11)


def test_open_ended_is_watch_without_date():
    result = compute_deadline(date(2026, 3, 3), rule_kind="OPEN_ENDED", offset_days=None, computation="CALENDAR_INCLUSIVE")
    assert result.due_date is None
    assert result.alert_kind == "WATCH"
