"""TDD tests for AuditLogRepository — written BEFORE implementation."""
from __future__ import annotations

from app.db.repositories.audit_log import AuditLogRepository
from app.db.repositories.tutor import TutorRepository


async def _make_tutor(db_session, tg_id: int = 4001):
    tutor, _ = await TutorRepository(db_session).get_or_create(tg_user_id=tg_id)
    return tutor


async def test_log_persists_action_without_payload(db_session):
    tutor = await _make_tutor(db_session)
    repo = AuditLogRepository(db_session)
    entry = await repo.log(tutor_id=tutor.id, action="bot_silenced")
    assert entry.id is not None
    assert entry.action == "bot_silenced"
    assert entry.payload_json is None
    assert entry.tutor_id == tutor.id


async def test_log_persists_payload_dict(db_session):
    tutor = await _make_tutor(db_session)
    repo = AuditLogRepository(db_session)
    payload = {"intent": "reschedule", "confidence": 0.91, "from": "2026-06-01T15:00"}
    entry = await repo.log(tutor_id=tutor.id, action="reschedule_applied", payload=payload)
    assert entry.payload_json == payload


async def test_list_for_tutor_returns_newest_first(db_session):
    tutor = await _make_tutor(db_session)
    repo = AuditLogRepository(db_session)
    await repo.log(tutor_id=tutor.id, action="first")
    await repo.log(tutor_id=tutor.id, action="second")
    await repo.log(tutor_id=tutor.id, action="third")
    entries = await repo.list_for_tutor(tutor.id)
    assert [e.action for e in entries] == ["third", "second", "first"]


async def test_list_for_tutor_respects_limit(db_session):
    tutor = await _make_tutor(db_session, tg_id=4002)
    repo = AuditLogRepository(db_session)
    for i in range(5):
        await repo.log(tutor_id=tutor.id, action=f"a{i}")
    entries = await repo.list_for_tutor(tutor.id, limit=2)
    assert len(entries) == 2


async def test_list_for_tutor_isolates_by_tutor(db_session):
    a = await _make_tutor(db_session, tg_id=4101)
    b = await _make_tutor(db_session, tg_id=4102)
    repo = AuditLogRepository(db_session)
    await repo.log(tutor_id=a.id, action="from_a")
    await repo.log(tutor_id=b.id, action="from_b")
    entries_a = await repo.list_for_tutor(a.id)
    assert [e.action for e in entries_a] == ["from_a"]
