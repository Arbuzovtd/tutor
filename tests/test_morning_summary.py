"""Tests for the morning summary builder (pure function)."""
from __future__ import annotations

from datetime import date, datetime, timezone

from app.db.models import Lesson, PersonalBlock, Student
from app.services.morning_summary import build_morning_summary


def _lesson(when: datetime, status: str = "scheduled") -> Lesson:
    lesson = Lesson(tutor_id=1, student_id=1, scheduled_at=when, duration_min=60, status=status)
    lesson.id = 1
    return lesson


def _student(name: str | None = "Петя") -> Student:
    s = Student(tutor_id=1, telegram_user_id=1, telegram_chat_id=1, name=name)
    s.id = 1
    return s


def _block(start: datetime, end: datetime, label: str = "обед") -> PersonalBlock:
    b = PersonalBlock(tutor_id=1, starts_at=start, ends_at=end, label=label)
    b.id = 1
    return b


TODAY = date(2026, 5, 11)
TZ = "Europe/Moscow"


def test_free_day_message():
    msg = build_morning_summary(today_local=TODAY, tz_name=TZ, lessons=[], blocks=[])
    assert "Свободный день" in msg
    assert "2026-05-11" in msg


def test_summary_lists_lessons_in_local_time():
    when = datetime(2026, 5, 11, 7, 0, tzinfo=timezone.utc)  # 10:00 MSK
    msg = build_morning_summary(
        today_local=TODAY,
        tz_name=TZ,
        lessons=[(_lesson(when), _student("Петя"))],
        blocks=[],
    )
    assert "Уроки" in msg
    assert "10:00" in msg
    assert "Петя" in msg


def test_summary_includes_blocks_section():
    s = datetime(2026, 5, 11, 11, 0, tzinfo=timezone.utc)  # 14:00 MSK
    e = datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc)  # 15:00 MSK
    msg = build_morning_summary(
        today_local=TODAY, tz_name=TZ, lessons=[], blocks=[_block(s, e)]
    )
    assert "Личные блоки" in msg
    assert "14:00-15:00" in msg
    assert "обед" in msg


def test_summary_shows_pending_review_count():
    msg = build_morning_summary(
        today_local=TODAY, tz_name=TZ, lessons=[], blocks=[], pending_review_count=3
    )
    assert "3" in msg
    assert "сообщений" in msg


def test_summary_pending_count_singular_form():
    msg = build_morning_summary(
        today_local=TODAY, tz_name=TZ, lessons=[], blocks=[], pending_review_count=1
    )
    assert "1 сообщение" in msg
