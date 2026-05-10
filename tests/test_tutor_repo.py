"""TDD tests for TutorRepository — written BEFORE the implementation."""
from __future__ import annotations

from app.db.repositories.tutor import TutorRepository


async def test_get_or_create_creates_when_missing(db_session):
    repo = TutorRepository(db_session)
    tutor, created = await repo.get_or_create(tg_user_id=12345)
    assert created is True
    assert tutor.id is not None
    assert tutor.telegram_user_id == 12345
    assert tutor.disclosure_mode == "pretend"  # default per project decision
    assert tutor.is_active is True


async def test_get_or_create_returns_existing(db_session):
    repo = TutorRepository(db_session)
    first, _ = await repo.get_or_create(tg_user_id=999)
    second, created = await repo.get_or_create(tg_user_id=999)
    assert created is False
    assert second.id == first.id


async def test_get_by_telegram_user_id_returns_none_when_missing(db_session):
    repo = TutorRepository(db_session)
    result = await repo.get_by_telegram_user_id(tg_user_id=666)
    assert result is None


async def test_create_with_explicit_name_and_timezone(db_session):
    repo = TutorRepository(db_session)
    tutor = await repo.create(tg_user_id=5555, name="Anna", timezone="Asia/Almaty")
    assert tutor.name == "Anna"
    assert tutor.timezone == "Asia/Almaty"
