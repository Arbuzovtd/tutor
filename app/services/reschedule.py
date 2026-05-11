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
from datetime import datetime, timedelta
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.types import IntentKind, IntentResult
from app.db.models import Tutor
from app.db.repositories.business_connection import BusinessConnectionRepository
from app.db.repositories.chat_message import ChatMessageRepository
from app.db.repositories.student import StudentRepository

# Window during which a tutor's manual reply silences the bot in this chat.
HANDOFF_WINDOW = timedelta(minutes=60)
# Below this, intents are queued for tutor review instead of auto-replied.
INTENT_CONFIDENCE_THRESHOLD = 0.7

# Stub replies for cycle 4 — replaced with calendar-aware text in cycle 5.
_STUB_RESCHEDULE_REPLY = "Понял, сейчас уточню расписание и вернусь через минуту."
_STUB_CANCEL_REPLY = "Принял, проверю отмену и подтвержу."


class IntentParserProtocol(Protocol):
    async def parse(self, text: str, current_datetime: datetime) -> IntentResult: ...


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
    parser: IntentParserProtocol | None = None,
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

    # Tutor typing in their own client → record as outbound_tutor, no Student row.
    if from_user_id == tutor.telegram_user_id:
        await msg_repo.record_outbound(
            tutor_id=tutor.id,
            business_connection_id=connection_id,
            text=text,
            direction="outbound_tutor",
            telegram_message_id=telegram_message_id,
        )
        return HandleResult(action="tutor_outbound")

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

    # Handoff: if tutor manually replied in this chat within the window, stay silent.
    last_tutor_at = await msg_repo.last_tutor_outbound_at(connection_id)
    if last_tutor_at is not None and now - last_tutor_at < HANDOFF_WINDOW:
        return HandleResult(action="tutor_handoff")

    if parser is None:
        return HandleResult(action="received")

    intent = await parser.parse(text, current_datetime=now)
    high_conf = intent.confidence >= INTENT_CONFIDENCE_THRESHOLD

    if high_conf and intent.kind == IntentKind.RESCHEDULE:
        await msg_repo.record_outbound(
            tutor_id=tutor.id,
            business_connection_id=connection_id,
            text=_STUB_RESCHEDULE_REPLY,
            direction="outbound_bot",
            student_id=student.id,
            intent=intent.kind.value,
            confidence=intent.confidence,
        )
        return HandleResult(action="reschedule_pending", reply_text=_STUB_RESCHEDULE_REPLY)

    if high_conf and intent.kind == IntentKind.CANCEL:
        await msg_repo.record_outbound(
            tutor_id=tutor.id,
            business_connection_id=connection_id,
            text=_STUB_CANCEL_REPLY,
            direction="outbound_bot",
            student_id=student.id,
            intent=intent.kind.value,
            confidence=intent.confidence,
        )
        return HandleResult(action="cancel_pending", reply_text=_STUB_CANCEL_REPLY)

    return HandleResult(action="needs_tutor_review")
