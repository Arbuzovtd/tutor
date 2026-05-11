"""Reschedule Decision Engine — entry point for incoming business_message updates.

Tutor-in-the-loop flow: on a high-confidence intent the bot
1) sends a short ack to the student in the business chat,
2) pings the tutor in their private chat with the bot with inline buttons.

The router is the only place that calls Telegram APIs. The engine returns
structured data describing what should be sent where; the router does the I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.types import IntentKind, IntentResult
from app.db.models import Tutor
from app.db.repositories.audit_log import AuditLogRepository
from app.db.repositories.business_connection import BusinessConnectionRepository
from app.db.repositories.chat_message import ChatMessageRepository
from app.db.repositories.student import StudentRepository

# Window during which a tutor's manual reply silences the bot in this chat.
HANDOFF_WINDOW = timedelta(minutes=60)
# Below this, intents are queued for tutor review instead of auto-replied.
INTENT_CONFIDENCE_THRESHOLD = 0.7

# Acks sent to the student while we wait for the tutor's confirmation.
_RESCHEDULE_ACK = "Сейчас уточню расписание и вернусь через пару минут."
_CANCEL_ACK = "Сейчас уточню и подтвержу отмену."


class IntentParserProtocol(Protocol):
    async def parse(self, text: str, current_datetime: datetime) -> IntentResult: ...


@dataclass(frozen=True)
class TutorNotification:
    """Everything the router needs to ping the tutor in their DM with the bot.

    `chat_message_id` is the inbound row id and serves as the lookup key when
    the tutor taps an inline button later (callback_data = "approve:{id}" etc).
    """

    tutor_telegram_id: int
    text: str
    chat_message_id: int


@dataclass(frozen=True)
class HandleResult:
    action: str
    reply_text: str | None = None
    tutor_notification: TutorNotification | None = None


def _format_tutor_ping(
    *,
    student_name: str | None,
    student_id: int,
    intent_kind: IntentKind,
    raw_text: str,
    target_dt: datetime | None,
    new_dt: datetime | None,
) -> str:
    name = student_name or f"ученик #{student_id}"
    action_human = {
        IntentKind.RESCHEDULE: "перенос занятия",
        IntentKind.CANCEL: "отмена занятия",
    }.get(intent_kind, intent_kind.value)
    lines = [
        f"🔔 {name}: «{raw_text}»",
        f"Понял как: {action_human}.",
    ]
    if target_dt is not None:
        lines.append(f"С: {target_dt.strftime('%d.%m %H:%M')}")
    if new_dt is not None:
        lines.append(f"На: {new_dt.strftime('%d.%m %H:%M')}")
    return "\n".join(lines)


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
    inbound = await msg_repo.record_inbound(
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

    if high_conf and intent.kind in (IntentKind.RESCHEDULE, IntentKind.CANCEL):
        ack = _RESCHEDULE_ACK if intent.kind == IntentKind.RESCHEDULE else _CANCEL_ACK
        action = "reschedule_pending" if intent.kind == IntentKind.RESCHEDULE else "cancel_pending"

        await msg_repo.record_outbound(
            tutor_id=tutor.id,
            business_connection_id=connection_id,
            text=ack,
            direction="outbound_bot",
            student_id=student.id,
            intent=intent.kind.value,
            confidence=intent.confidence,
        )
        await AuditLogRepository(session).log(
            tutor_id=tutor.id,
            action="pending_review",
            payload={
                "chat_message_id": inbound.id,
                "student_id": student.id,
                "intent": intent.kind.value,
                "confidence": intent.confidence,
                "target_datetime": intent.target_datetime.isoformat()
                if intent.target_datetime
                else None,
                "new_datetime": intent.new_datetime.isoformat()
                if intent.new_datetime
                else None,
            },
        )
        notification = TutorNotification(
            tutor_telegram_id=tutor.telegram_user_id,
            chat_message_id=inbound.id,
            text=_format_tutor_ping(
                student_name=student.name,
                student_id=student.id,
                intent_kind=intent.kind,
                raw_text=text,
                target_dt=intent.target_datetime,
                new_dt=intent.new_datetime,
            ),
        )
        return HandleResult(action=action, reply_text=ack, tutor_notification=notification)

    return HandleResult(action="needs_tutor_review")
