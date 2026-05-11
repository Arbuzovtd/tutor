"""Tests for pure message formatters."""
from __future__ import annotations

from datetime import date, datetime, timezone

from app.bot.format import (
    format_blocks_message,
    format_lessons_message,
    format_students_message,
    format_today_message,
)
from app.db.models import Lesson, PersonalBlock, Student


def _block(starts_at: datetime, ends_at: datetime, *, label: str | None = "обед", block_id: int = 1) -> PersonalBlock:
    b = PersonalBlock(tutor_id=1, starts_at=starts_at, ends_at=ends_at, label=label)
    b.id = block_id
    return b


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


def test_format_today_empty_says_nothing():
    msg = format_today_message([], date_local=date(2026, 5, 11), tz_name="Europe/Moscow")
    assert "пусто" in msg
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


def test_format_students_empty():
    msg = format_students_message([])
    assert "пока нет" in msg.lower() or "нет" in msg.lower()


def test_format_students_lists_with_subject_and_grade():
    s = _student("Петя")
    s.subject = "математика"
    s.grade = "9"
    msg = format_students_message([s])
    assert "Петя" in msg
    assert "математика" in msg
    assert "9" in msg


def test_format_lessons_empty():
    msg = format_lessons_message([], tz_name="Europe/Moscow")
    assert "нет" in msg.lower()


def test_format_lessons_renders_date_and_time():
    # 07:00 UTC May 13 = 10:00 MSK May 13
    when = datetime(2026, 5, 13, 7, 0, tzinfo=timezone.utc)
    rows = [(_lesson(when), _student("Аня"))]
    msg = format_lessons_message(rows, tz_name="Europe/Moscow")
    assert "13.05" in msg
    assert "10:00" in msg
    assert "Аня" in msg


def test_format_today_includes_blocks_below_lessons():
    when = datetime(2026, 5, 11, 7, 0, tzinfo=timezone.utc)  # 10:00 MSK
    rows = [(_lesson(when), _student("Петя"))]
    block_start = datetime(2026, 5, 11, 11, 0, tzinfo=timezone.utc)  # 14:00 MSK
    block_end = datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc)  # 15:00 MSK
    blocks = [_block(block_start, block_end, label="обед")]
    msg = format_today_message(
        rows, date_local=date(2026, 5, 11), tz_name="Europe/Moscow", blocks=blocks
    )
    assert "10:00" in msg
    assert "Петя" in msg
    assert "14:00" in msg
    assert "обед" in msg
    assert "🚫" in msg


def test_format_today_only_blocks_no_lessons():
    block_start = datetime(2026, 5, 11, 11, 0, tzinfo=timezone.utc)
    block_end = datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc)
    blocks = [_block(block_start, block_end)]
    msg = format_today_message(
        [], date_local=date(2026, 5, 11), tz_name="Europe/Moscow", blocks=blocks
    )
    assert "🚫" in msg


def test_format_blocks_empty():
    assert "нет" in format_blocks_message([], tz_name="Europe/Moscow").lower()


def test_format_blocks_renders_time_range_same_day():
    starts = datetime(2026, 5, 11, 11, 0, tzinfo=timezone.utc)  # 14:00 MSK
    ends = datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc)  # 15:00 MSK
    msg = format_blocks_message([_block(starts, ends, block_id=42)], tz_name="Europe/Moscow")
    assert "#42" in msg
    assert "11.05 14:00" in msg
    assert "15:00" in msg


def test_format_blocks_multi_day_shows_date_range():
    # 2026-06-20 00:00 MSK to 2026-06-26 00:00 MSK (June 20-25 inclusive)
    starts = datetime(2026, 6, 19, 21, 0, tzinfo=timezone.utc)  # 00:00 MSK June 20
    ends = datetime(2026, 6, 25, 21, 0, tzinfo=timezone.utc)  # 00:00 MSK June 26
    msg = format_blocks_message(
        [_block(starts, ends, label="каникулы")], tz_name="Europe/Moscow"
    )
    assert "20.06" in msg
    assert "25.06" in msg
    assert "каникулы" in msg
