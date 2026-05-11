"""TDD tests for LessonRepository — written BEFORE implementation."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db.models import Student
from app.db.repositories.lesson import LessonRepository
from app.db.repositories.tutor import TutorRepository


async def _make_tutor_and_student(db_session, tg_tutor: int = 2001, tg_student: int = 3001):
    tutor, _ = await TutorRepository(db_session).get_or_create(tg_user_id=tg_tutor)
    student = Student(
        tutor_id=tutor.id,
        telegram_user_id=tg_student,
        telegram_chat_id=tg_student,
        name="Test Student",
    )
    db_session.add(student)
    await db_session.flush()
    return tutor, student


async def test_create_persists_lesson_with_defaults(db_session):
    tutor, student = await _make_tutor_and_student(db_session)
    repo = LessonRepository(db_session)
    when = datetime(2026, 6, 1, 15, 0, tzinfo=timezone.utc)
    lesson = await repo.create(
        tutor_id=tutor.id,
        student_id=student.id,
        scheduled_at=when,
    )
    assert lesson.id is not None
    assert lesson.duration_min == 60
    assert lesson.status == "scheduled"
    assert lesson.calendar_event_id is None


async def test_get_by_calendar_event_id_returns_match(db_session):
    tutor, student = await _make_tutor_and_student(db_session)
    repo = LessonRepository(db_session)
    when = datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc)
    created = await repo.create(
        tutor_id=tutor.id,
        student_id=student.id,
        scheduled_at=when,
        calendar_event_id="gcal_evt_42",
    )
    found = await repo.get_by_calendar_event_id("gcal_evt_42")
    assert found is not None
    assert found.id == created.id


async def test_get_by_calendar_event_id_missing_returns_none(db_session):
    repo = LessonRepository(db_session)
    assert await repo.get_by_calendar_event_id("nope") is None


async def test_list_upcoming_for_student_excludes_past(db_session):
    tutor, student = await _make_tutor_and_student(db_session)
    repo = LessonRepository(db_session)
    now = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
    past = await repo.create(
        tutor_id=tutor.id,
        student_id=student.id,
        scheduled_at=now - timedelta(days=1),
    )
    future_near = await repo.create(
        tutor_id=tutor.id,
        student_id=student.id,
        scheduled_at=now + timedelta(hours=2),
    )
    future_far = await repo.create(
        tutor_id=tutor.id,
        student_id=student.id,
        scheduled_at=now + timedelta(days=3),
    )

    upcoming = await repo.list_upcoming_for_student(student.id, now=now)
    upcoming_ids = [lesson.id for lesson in upcoming]
    assert past.id not in upcoming_ids
    assert upcoming_ids == [future_near.id, future_far.id]  # sorted by scheduled_at asc


async def test_update_status_changes_field(db_session):
    tutor, student = await _make_tutor_and_student(db_session)
    repo = LessonRepository(db_session)
    when = datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc)
    lesson = await repo.create(
        tutor_id=tutor.id,
        student_id=student.id,
        scheduled_at=when,
    )
    updated = await repo.update_status(lesson.id, "cancelled")
    assert updated is not None
    assert updated.status == "cancelled"


async def test_update_status_missing_returns_none(db_session):
    repo = LessonRepository(db_session)
    assert await repo.update_status(999_999, "cancelled") is None
