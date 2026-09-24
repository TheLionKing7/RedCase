from datetime import date

from app.deadline_detector import DetectedDate, extract_delivery_dates


def test_extracts_explicit_ruling_and_judgment_dates():
    found = extract_delivery_dates(
        '{"ruling delivered 2026-03-03", "judgment delivered 2026-04-10"}'
    )
    assert found == (
        DetectedDate("delivery/date of ruling", date(2026, 3, 3)),
        DetectedDate("delivery/date of judgment", date(2026, 4, 10)),
    )


def test_ignores_dates_without_delivery_language():
    assert extract_delivery_dates('{"hearing": "2026-03-03"}') == ()