"""Tests for PersonalBlockRepository."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db.repositories.personal_block import PersonalBlockRepository
from app.db.repositories.tutor import TutorRepository


async def _make_tutor(db_session, tg_id: int = 7001):
    tutor, _ = await TutorRepository(db_session).get_or_create(tg_user_id=tg_id)
    return tutor


async def test_create_and_list_upcoming(db_session):
    tutor = await _make_tutor(db_session)
    repo = PersonalBlockRepository(db_session)
    now = datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc)
    await repo.create(
        tutor_id=tutor.id,
        starts_at=now + timedelta(hours=1),
        ends_at=now + timedelta(hours=2),
        label="обед",
    )
    blocks = await repo.list_upcoming_for_tutor(tutor_id=tutor.id, now=now)
    assert len(blocks) == 1
    assert blocks[0].label == "обед"


async def test_list_upcoming_excludes_past(db_session):
    tutor = await _make_tutor(db_session, tg_id=7002)
    repo = PersonalBlockRepository(db_session)
    now = datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc)
    await repo.create(
        tutor_id=tutor.id,
        starts_at=now - timedelta(hours=2),
        ends_at=now - timedelta(hours=1),
        label="прошлое",
    )
    blocks = await repo.list_upcoming_for_tutor(tutor_id=tutor.id, now=now)
    assert blocks == []


async def test_list_in_range_includes_overlap(db_session):
    tutor = await _make_tutor(db_session, tg_id=7003)
    repo = PersonalBlockRepository(db_session)
    base = datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc)
    # block 10:00–13:00; range query 11:00–12:30 → must include
    await repo.create(
        tutor_id=tutor.id,
        starts_at=base - timedelta(hours=2),
        ends_at=base + timedelta(hours=1),
        label="долгий",
    )
    blocks = await repo.list_for_tutor_in_range(
        tutor_id=tutor.id,
        range_start=base - timedelta(hours=1),
        range_end=base + timedelta(minutes=30),
    )
    assert len(blocks) == 1


async def test_isolation_per_tutor(db_session):
    a = await _make_tutor(db_session, tg_id=7011)
    b = await _make_tutor(db_session, tg_id=7012)
    repo = PersonalBlockRepository(db_session)
    now = datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc)
    await repo.create(
        tutor_id=a.id,
        starts_at=now + timedelta(hours=1),
        ends_at=now + timedelta(hours=2),
    )
    assert await repo.list_upcoming_for_tutor(tutor_id=b.id, now=now) == []


async def test_delete_by_id_only_own(db_session):
    a = await _make_tutor(db_session, tg_id=7021)
    b = await _make_tutor(db_session, tg_id=7022)
    repo = PersonalBlockRepository(db_session)
    now = datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc)
    block = await repo.create(
        tutor_id=a.id, starts_at=now + timedelta(hours=1), ends_at=now + timedelta(hours=2)
    )
    # Tutor B can't delete A's block
    assert await repo.delete_by_id(tutor_id=b.id, block_id=block.id) is False
    # Tutor A can
    assert await repo.delete_by_id(tutor_id=a.id, block_id=block.id) is True
    # Idempotent: second delete returns False
    assert await repo.delete_by_id(tutor_id=a.id, block_id=block.id) is False
