"""TDD tests for ChatMessageRepository — written BEFORE implementation.

Idempotency is the load-bearing invariant: when Telegram retries the same
business_message update, the second call to record_inbound must NOT create
a duplicate row. The DB UniqueConstraint(business_connection_id,
telegram_message_id) enforces it; the repo must expose a cheap exists check.
"""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.repositories.chat_message import ChatMessageRepository
from app.db.repositories.tutor import TutorRepository


async def _make_tutor(db_session, tg_id: int = 1001):
    tutor, _ = await TutorRepository(db_session).get_or_create(tg_user_id=tg_id)
    return tutor


async def test_exists_by_telegram_msg_false_when_missing(db_session):
    repo = ChatMessageRepository(db_session)
    assert await repo.exists_by_telegram_msg("conn_x", 555) is False


async def test_record_inbound_persists_message(db_session):
    tutor = await _make_tutor(db_session)
    repo = ChatMessageRepository(db_session)
    msg = await repo.record_inbound(
        tutor_id=tutor.id,
        business_connection_id="conn_a",
        telegram_message_id=10,
        text="перенеси на завтра",
    )
    assert msg.id is not None
    assert msg.direction == "inbound"
    assert msg.text == "перенеси на завтра"
    assert msg.tutor_id == tutor.id


async def test_exists_by_telegram_msg_true_after_record(db_session):
    tutor = await _make_tutor(db_session)
    repo = ChatMessageRepository(db_session)
    await repo.record_inbound(
        tutor_id=tutor.id,
        business_connection_id="conn_b",
        telegram_message_id=20,
        text="hi",
    )
    assert await repo.exists_by_telegram_msg("conn_b", 20) is True


async def test_record_inbound_duplicate_raises_integrity_error(db_session):
    tutor = await _make_tutor(db_session)
    repo = ChatMessageRepository(db_session)
    await repo.record_inbound(
        tutor_id=tutor.id,
        business_connection_id="conn_c",
        telegram_message_id=30,
        text="first",
    )
    with pytest.raises(IntegrityError):
        await repo.record_inbound(
            tutor_id=tutor.id,
            business_connection_id="conn_c",
            telegram_message_id=30,
            text="second",
        )


async def test_record_outbound_default_direction(db_session):
    tutor = await _make_tutor(db_session)
    repo = ChatMessageRepository(db_session)
    msg = await repo.record_outbound(
        tutor_id=tutor.id,
        business_connection_id="conn_d",
        text="ok, перенёс",
    )
    assert msg.direction == "outbound_bot"
    assert msg.telegram_message_id is None


async def test_record_outbound_with_intent_and_confidence(db_session):
    tutor = await _make_tutor(db_session)
    repo = ChatMessageRepository(db_session)
    msg = await repo.record_outbound(
        tutor_id=tutor.id,
        business_connection_id="conn_e",
        text="reply",
        intent="reschedule",
        confidence=0.92,
    )
    assert msg.intent == "reschedule"
    assert msg.confidence == pytest.approx(0.92)
