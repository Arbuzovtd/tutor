"""Tests for the 4096-char overflow guard in handle_business_message."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.db.models import ChatMessage
from app.db.repositories.business_connection import BusinessConnectionRepository
from app.db.repositories.tutor import TutorRepository
from app.services.reschedule import MAX_TEXT_LEN, handle_business_message


async def _make_connected_tutor(db_session, *, tg_id: int, conn_id: str):
    tutor, _ = await TutorRepository(db_session).get_or_create(tg_user_id=tg_id)
    tutor.is_registered = True
    await BusinessConnectionRepository(db_session).upsert(
        tutor_id=tutor.id,
        connection_id=conn_id,
        user_chat_id=999,
        is_enabled=True,
        can_reply=True,
    )
    await db_session.flush()
    return tutor


async def test_long_student_text_is_truncated_before_persist(db_session):
    await _make_connected_tutor(db_session, tg_id=20001, conn_id="conn_big")
    huge = "А" * 5000
    await handle_business_message(
        session=db_session,
        connection_id="conn_big",
        telegram_message_id=1,
        from_user_id=22222,
        chat_id=22222,
        text=huge,
        now=datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc),
    )
    stored = (
        await db_session.execute(
            select(ChatMessage).where(ChatMessage.business_connection_id == "conn_big")
        )
    ).scalar_one()
    assert len(stored.text) <= MAX_TEXT_LEN + 1  # +1 for the trailing ellipsis
    assert stored.text.endswith("…")


async def test_short_text_is_not_truncated(db_session):
    await _make_connected_tutor(db_session, tg_id=20002, conn_id="conn_small")
    await handle_business_message(
        session=db_session,
        connection_id="conn_small",
        telegram_message_id=2,
        from_user_id=22223,
        chat_id=22223,
        text="привет",
        now=datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc),
    )
    stored = (
        await db_session.execute(
            select(ChatMessage).where(ChatMessage.business_connection_id == "conn_small")
        )
    ).scalar_one()
    assert stored.text == "привет"
