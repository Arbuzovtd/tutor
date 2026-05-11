"""Callback handlers for the tutor-in-the-loop review flow.

When a student sends a high-confidence reschedule/cancel, the engine pings the
tutor in their private chat with the bot via inline keyboard:

    🔔 Петя: «перенеси на четверг»
    [✅ Подтвердить] [❌ Отказать]

Tap → callback_data="approve:42" / "reject:42" where 42 is chat_messages.id.
We look up the inbound row, find its business_connection_id, and send the
final reply to the student through the business chat.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChatMessage
from app.db.repositories.audit_log import AuditLogRepository
from app.db.repositories.chat_message import ChatMessageRepository

log = logging.getLogger(__name__)
router = Router(name="review")


APPROVE_TEXT = "Подтверждаю изменение. Зафиксировал."
REJECT_TEXT = "К сожалению, в это время не получится. Когда тебе ещё удобно?"


def build_review_keyboard(chat_message_id: int) -> InlineKeyboardMarkup:
    """Inline keyboard for the tutor's review ping."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить", callback_data=f"approve:{chat_message_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Отказать", callback_data=f"reject:{chat_message_id}"
                ),
            ]
        ]
    )


async def _resolve(
    query: CallbackQuery,
    session: AsyncSession,
    *,
    action: str,
    reply_text: str,
) -> None:
    """Shared logic for approve/reject. Loads inbound message, replies in business chat."""
    if query.data is None or ":" not in query.data:
        await query.answer("Некорректные данные.")
        return
    try:
        chat_message_id = int(query.data.split(":", 1)[1])
    except ValueError:
        await query.answer("Некорректный идентификатор.")
        return

    inbound = await session.get(ChatMessage, chat_message_id)
    if inbound is None or inbound.direction != "inbound":
        await query.answer("Сообщение не найдено или уже обработано.")
        return
    if inbound.business_connection_id is None or inbound.student_id is None:
        await query.answer("Недостаточно данных для ответа.")
        return

    msg_repo = ChatMessageRepository(session)
    await msg_repo.record_outbound(
        tutor_id=inbound.tutor_id,
        business_connection_id=inbound.business_connection_id,
        text=reply_text,
        direction="outbound_bot",
        student_id=inbound.student_id,
        intent=action,
    )
    await AuditLogRepository(session).log(
        tutor_id=inbound.tutor_id,
        action=action,
        payload={"chat_message_id": chat_message_id},
    )

    if query.bot is not None and inbound.business_connection_id is not None:
        # Find the original chat by replaying the student's user_chat_id via BC
        # Simpler: send to a saved student.telegram_chat_id
        from app.db.models import Student

        student = await session.get(Student, inbound.student_id)
        if student is not None:
            await query.bot.send_message(
                chat_id=student.telegram_chat_id,
                business_connection_id=inbound.business_connection_id,
                text=reply_text,
            )

    # Edit the tutor's ping to show resolution
    if query.message is not None:
        try:
            await query.message.edit_text(
                f"{query.message.text}\n\n— {action.upper()}", reply_markup=None
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("could not edit review message: %s", exc)
    await query.answer(f"{action} ✓")


@router.callback_query(F.data.startswith("approve:"))
async def on_approve(query: CallbackQuery, session: AsyncSession) -> None:
    await _resolve(query, session, action="approved", reply_text=APPROVE_TEXT)


@router.callback_query(F.data.startswith("reject:"))
async def on_reject(query: CallbackQuery, session: AsyncSession) -> None:
    await _resolve(query, session, action="rejected", reply_text=REJECT_TEXT)
