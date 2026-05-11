"""TDD tests for StudentRepository.get_or_create_by_telegram_id."""
from __future__ import annotations

from app.db.repositories.student import StudentRepository
from app.db.repositories.tutor import TutorRepository


async def _make_tutor(db_session, tg_id: int = 9001):
    tutor, _ = await TutorRepository(db_session).get_or_create(tg_user_id=tg_id)
    return tutor


async def test_get_or_create_inserts_first_time(db_session):
    tutor = await _make_tutor(db_session)
    repo = StudentRepository(db_session)
    student, created = await repo.get_or_create_by_telegram_id(
        tutor_id=tutor.id,
        telegram_user_id=11111,
        telegram_chat_id=11111,
    )
    assert created is True
    assert student.id is not None
    assert student.tutor_id == tutor.id
    assert student.telegram_user_id == 11111


async def test_get_or_create_reuses_existing(db_session):
    tutor = await _make_tutor(db_session)
    repo = StudentRepository(db_session)
    first, created_a = await repo.get_or_create_by_telegram_id(
        tutor_id=tutor.id, telegram_user_id=22222, telegram_chat_id=22222
    )
    second, created_b = await repo.get_or_create_by_telegram_id(
        tutor_id=tutor.id, telegram_user_id=22222, telegram_chat_id=22222
    )
    assert created_a is True
    assert created_b is False
    assert second.id == first.id


async def test_same_telegram_id_isolated_per_tutor(db_session):
    """Multi-tenant: tutor A and tutor B can both have student with TG id 333."""
    tutor_a = await _make_tutor(db_session, tg_id=9101)
    tutor_b = await _make_tutor(db_session, tg_id=9102)
    repo = StudentRepository(db_session)
    student_a, _ = await repo.get_or_create_by_telegram_id(
        tutor_id=tutor_a.id, telegram_user_id=333, telegram_chat_id=333
    )
    student_b, _ = await repo.get_or_create_by_telegram_id(
        tutor_id=tutor_b.id, telegram_user_id=333, telegram_chat_id=333
    )
    assert student_a.id != student_b.id
    assert student_a.tutor_id != student_b.tutor_id
