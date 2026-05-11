"""Tests for AuditLogRepository.count_pending_review_unresolved (M-2 fix)."""
from __future__ import annotations

from app.db.repositories.audit_log import AuditLogRepository
from app.db.repositories.tutor import TutorRepository


async def _make_tutor(db_session, tg_id: int):
    tutor, _ = await TutorRepository(db_session).get_or_create(tg_user_id=tg_id)
    return tutor


async def test_count_only_unresolved(db_session):
    tutor = await _make_tutor(db_session, tg_id=30001)
    repo = AuditLogRepository(db_session)
    # 3 pending; resolve 2 of them
    await repo.log(tutor_id=tutor.id, action="pending_review", payload={"chat_message_id": 1})
    await repo.log(tutor_id=tutor.id, action="pending_review", payload={"chat_message_id": 2})
    await repo.log(tutor_id=tutor.id, action="pending_review", payload={"chat_message_id": 3})
    await repo.log(tutor_id=tutor.id, action="approved", payload={"chat_message_id": 1})
    await repo.log(tutor_id=tutor.id, action="rejected", payload={"chat_message_id": 2})

    unresolved = await repo.count_pending_review_unresolved(tutor_id=tutor.id)
    assert unresolved == 1


async def test_count_zero_when_all_resolved(db_session):
    tutor = await _make_tutor(db_session, tg_id=30002)
    repo = AuditLogRepository(db_session)
    await repo.log(tutor_id=tutor.id, action="pending_review", payload={"chat_message_id": 10})
    await repo.log(tutor_id=tutor.id, action="approved", payload={"chat_message_id": 10})
    assert await repo.count_pending_review_unresolved(tutor_id=tutor.id) == 0


async def test_count_isolates_per_tutor(db_session):
    a = await _make_tutor(db_session, tg_id=30011)
    b = await _make_tutor(db_session, tg_id=30012)
    repo = AuditLogRepository(db_session)
    await repo.log(tutor_id=a.id, action="pending_review", payload={"chat_message_id": 100})
    await repo.log(tutor_id=b.id, action="pending_review", payload={"chat_message_id": 200})
    # Resolving A's doesn't affect B
    await repo.log(tutor_id=a.id, action="approved", payload={"chat_message_id": 100})
    assert await repo.count_pending_review_unresolved(tutor_id=a.id) == 0
    assert await repo.count_pending_review_unresolved(tutor_id=b.id) == 1
