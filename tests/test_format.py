"""Tests for pure message formatters."""
from __future__ import annotations

from datetime import date, datetime, timezone

from app.bot.format import format_today_message
from app.db.models import Lesson, Student


def _lesson(scheduled_at: datetime, *, status: str = "scheduled", lesson_id: int = 1) -> Lesson:
    lesson = Lesson(
        tutor_id=1,
        student_id=1,
        scheduled_at=scheduled_at,
        duration_min=60,
        status=status,
    )
    lesson.id = lesson_id
    return lesson


def _student(name: str | None, *, student_id: int = 1) -> Student:
    s = Student(tutor_id=1, telegram_user_id=1, telegram_chat_id=1, name=name)
    s.id = student_id
    return s


def test_format_today_empty_says_no_lessons():
    msg = format_today_message([], date_local=date(2026, 5, 11), tz_name="Europe/Moscow")
    assert "уроков нет" in msg
    assert "2026-05-11" in msg


def test_format_today_renders_local_time_and_name():
    # 07:00 UTC = 10:00 MSK
    when = datetime(2026, 5, 11, 7, 0, tzinfo=timezone.utc)
    rows = [(_lesson(when), _student("Петя"))]
    msg = format_today_message(rows, date_local=date(2026, 5, 11), tz_name="Europe/Moscow")
    assert "10:00" in msg
    assert "Петя" in msg


def test_format_today_marks_cancelled_lessons():
    when = datetime(2026, 5, 11, 10, 0, tzinfo=timezone.utc)
    rows = [(_lesson(when, status="cancelled"), _student("Маша"))]
    msg = format_today_message(rows, date_local=date(2026, 5, 11), tz_name="Europe/Moscow")
    assert "[cancelled]" in msg


def test_format_today_falls_back_to_student_id_when_no_name():
    when = datetime(2026, 5, 11, 10, 0, tzinfo=timezone.utc)
    rows = [(_lesson(when), _student(name=None, student_id=42))]
    msg = format_today_message(rows, date_local=date(2026, 5, 11), tz_name="Europe/Moscow")
    assert "#42" in msg
