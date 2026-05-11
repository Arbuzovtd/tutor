"""TDD tests for handle_business_message service — Phase 5 entry point.

Cycle 1: idempotency + connection-not-found guard. No parser/calendar yet.
Subsequent cycles will layer in student identification, handoff detection,
intent routing, and calendar actions.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.db.repositories.business_connection import BusinessConnectionRepository
from app.db.repositories.chat_message import ChatMessageRepository
from app.db.repositories.tutor import TutorRepository
from app.services.reschedule import HandleResult, handle_business_message


NOW = datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc)


async def _make_connected_tutor(db_session, *, tg_id: int, conn_id: str, chat_id: int = 999):
    tutor, _ = await TutorRepository(db_session).get_or_create(tg_user_id=tg_id)
    tutor.is_registered = True
    await BusinessConnectionRepository(db_session).upsert(
        tutor_id=tutor.id,
        connection_id=conn_id,
        user_chat_id=chat_id,
        is_enabled=True,
        can_reply=True,
    )
    await db_session.flush()
    return tutor


async def test_unknown_connection_returns_silent_ignore(db_session):
    """If business_connection isn't in DB, service stays silent (no crash)."""
    result = await handle_business_message(
        session=db_session,
        connection_id="conn_never_seen",
        telegram_message_id=1,
        from_user_id=555,
        chat_id=555,
        text="привет",
        now=NOW,
    )
    assert result == HandleResult(action="unknown_connection", reply_text=None)


async def test_unregistered_tutor_is_silent(db_session):
    """Bot must not reply while tutor is mid-onboarding (is_registered=False)."""
    tutor, _ = await TutorRepository(db_session).get_or_create(tg_user_id=7001)
    # Note: is_registered stays default False
    await BusinessConnectionRepository(db_session).upsert(
        tutor_id=tutor.id,
        connection_id="conn_unreg",
        user_chat_id=42,
        is_enabled=True,
        can_reply=True,
    )
    await db_session.flush()

    result = await handle_business_message(
        session=db_session,
        connection_id="conn_unreg",
        telegram_message_id=2,
        from_user_id=42,
        chat_id=42,
        text="hi",
        now=NOW,
    )
    assert result.reply_text is None
    assert result.action == "unregistered_tutor"


async def test_duplicate_message_is_idempotent(db_session):
    """Second delivery of same Telegram message returns silent ignore, no new row."""
    tutor = await _make_connected_tutor(db_session, tg_id=7002, conn_id="conn_dup")
    msg_repo = ChatMessageRepository(db_session)
    # Simulate the first delivery already persisted.
    await msg_repo.record_inbound(
        tutor_id=tutor.id,
        business_connection_id="conn_dup",
        telegram_message_id=77,
        text="перенеси на завтра",
    )

    result = await handle_business_message(
        session=db_session,
        connection_id="conn_dup",
        telegram_message_id=77,
        from_user_id=12345,
        chat_id=12345,
        text="перенеси на завтра",
        now=NOW,
    )
    assert result == HandleResult(action="duplicate_ignored", reply_text=None)


async def test_first_message_persists_inbound_record(db_session):
    """A fresh message must be persisted as direction='inbound' before any other branching."""
    tutor = await _make_connected_tutor(db_session, tg_id=7003, conn_id="conn_fresh")
    result = await handle_business_message(
        session=db_session,
        connection_id="conn_fresh",
        telegram_message_id=88,
        from_user_id=22222,
        chat_id=22222,
        text="привет",
        now=NOW,
    )
    # Action is "received" for cycle 1; later cycles will branch to reschedule/cancel/etc.
    assert result.action == "received"
    # The inbound record must exist now.
    assert (
        await ChatMessageRepository(db_session).exists_by_telegram_msg("conn_fresh", 88)
        is True
    )
