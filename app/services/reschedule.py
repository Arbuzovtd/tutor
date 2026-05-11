"""Reschedule Decision Engine — entry point for incoming business_message updates.

Responsibilities (built up across TDD cycles):
1. Idempotency: dedupe Telegram retries by (business_connection_id, telegram_message_id)
2. Student identification: find or create Student by Telegram user id
3. Handoff detection: stay silent if the tutor recently replied themselves
4. Intent parsing → calendar action → reply
5. Low-confidence: queue draft for tutor review
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Tutor
from app.db.repositories.business_connection import BusinessConnectionRepository
from app.db.repositories.chat_message import ChatMessageRepository
from app.db.repositories.student import StudentRepository


@dataclass(frozen=True)
class HandleResult:
    """What the bot will do with this message.

    `reply_text` None means "stay silent". `action` is a stable string for audit.
    """

    action: str
    reply_text: str | None = None


async def handle_business_message(
    *,
    session: AsyncSession,
    connection_id: str,
    telegram_message_id: int,
    from_user_id: int,
    chat_id: int,
    text: str,
    now: datetime,
) -> HandleResult:
    bc_repo = BusinessConnectionRepository(session)
    bc = await bc_repo.get_by_connection_id(connection_id)
    if bc is None:
        return HandleResult(action="unknown_connection")

    tutor = await session.get(Tutor, bc.tutor_id)
    if tutor is None or not tutor.is_active or not tutor.is_registered:
        return HandleResult(action="unregistered_tutor")

    msg_repo = ChatMessageRepository(session)
    if await msg_repo.exists_by_telegram_msg(connection_id, telegram_message_id):
        return HandleResult(action="duplicate_ignored")

    student, _ = await StudentRepository(session).get_or_create_by_telegram_id(
        tutor_id=tutor.id,
        telegram_user_id=from_user_id,
        telegram_chat_id=chat_id,
    )
    await msg_repo.record_inbound(
        tutor_id=tutor.id,
        business_connection_id=connection_id,
        telegram_message_id=telegram_message_id,
        text=text,
        student_id=student.id,
    )
    return HandleResult(action="received")
