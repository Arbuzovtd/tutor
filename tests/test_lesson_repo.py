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


async def test_list_for_tutor_on_date_uses_tutor_timezone(db_session):
    """A lesson at 22:00 UTC on May 11 = 01:00 Moscow on May 12,
    so /today on May 12 (Moscow) should include it."""
    from datetime import date

    tutor, student = await _make_tutor_and_student(
        db_session, tg_tutor=4101, tg_student=4102
    )
    repo = LessonRepository(db_session)
    # 22:00 UTC May 11 = 01:00 MSK May 12
    await repo.create(
        tutor_id=tutor.id,
        student_id=student.id,
        scheduled_at=datetime(2026, 5, 11, 22, 0, tzinfo=timezone.utc),
    )
    rows = await repo.list_for_tutor_on_date(
        tutor_id=tutor.id, date_local=date(2026, 5, 12), tz_name="Europe/Moscow"
    )
    assert len(rows) == 1
    lesson, _ = rows[0]
    assert lesson.scheduled_at.astimezone(timezone.utc).hour == 22


async def test_list_for_tutor_on_date_isolates_per_tutor(db_session):
    """Other tutors' lessons must not show up."""
    from datetime import date

    tutor_a, student_a = await _make_tutor_and_student(
        db_session, tg_tutor=4201, tg_student=4202
    )
    tutor_b, student_b = await _make_tutor_and_student(
        db_session, tg_tutor=4203, tg_student=4204
    )
    repo = LessonRepository(db_session)
    when = datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc)
    await repo.create(tutor_id=tutor_a.id, student_id=student_a.id, scheduled_at=when)
    await repo.create(tutor_id=tutor_b.id, student_id=student_b.id, scheduled_at=when)

    rows = await repo.list_for_tutor_on_date(
        tutor_id=tutor_a.id, date_local=date(2026, 5, 12), tz_name="Europe/Moscow"
    )
    assert len(rows) == 1
    _, student = rows[0]
    assert student.id == student_a.id


async def test_list_for_tutor_on_date_empty(db_session):
    from datetime import date

    tutor, _ = await _make_tutor_and_student(
        db_session, tg_tutor=4301, tg_student=4302
    )
    repo = LessonRepository(db_session)
    rows = await repo.list_for_tutor_on_date(
        tutor_id=tutor.id, date_local=date(2026, 5, 12), tz_name="Europe/Moscow"
    )
    assert rows == []
