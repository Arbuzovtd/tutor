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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChatMessage, Student
from app.db.repositories.audit_log import AuditLogRepository
from app.db.repositories.chat_message import ChatMessageRepository
from app.db.repositories.tutor import TutorRepository

# Hard upper bound on chat_message_id from callback_data — guards against
# nonsensical input that would otherwise trigger pointless DB lookups.
_MAX_REASONABLE_PK = 2**31

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
    """Shared logic for approve/reject. Verifies the clicker is the owning tutor,
    then sends the chosen reply to the student via the business connection.
    """
    if query.data is None or ":" not in query.data:
        await query.answer("Некорректные данные.")
        return
    try:
        chat_message_id = int(query.data.split(":", 1)[1])
    except ValueError:
        await query.answer("Некорректный идентификатор.")
        return
    if not (0 < chat_message_id < _MAX_REASONABLE_PK):
        await query.answer("Некорректный идентификатор.")
        return
    if query.from_user is None:
        await query.answer("Кто вы?")
        return

    # Auth: the clicker must be the registered tutor who owns this inbound row.
    clicker = await TutorRepository(session).get_by_telegram_user_id(query.from_user.id)
    if clicker is None or not clicker.is_registered or not clicker.is_active:
        # Only audit when we have a tutor row to attach to (FK constraint).
        if clicker is not None:
            await AuditLogRepository(session).log(
                tutor_id=clicker.id,
                action="unauthorized_review_attempt",
                payload={
                    "clicker_tg_id": query.from_user.id,
                    "chat_message_id": chat_message_id,
                    "reason": "not_registered_or_inactive",
                },
            )
        else:
            log.warning(
                "review callback from unknown tg_id=%s for chat_message_id=%s",
                query.from_user.id,
                chat_message_id,
            )
        await query.answer("Нет доступа.")
        return

    inbound = await session.get(ChatMessage, chat_message_id)
    if inbound is None or inbound.direction != "inbound":
        await query.answer("Сообщение не найдено или уже обработано.")
        return
    if inbound.tutor_id != clicker.id:
        await AuditLogRepository(session).log(
            tutor_id=clicker.id,
            action="unauthorized_review_attempt",
            payload={
                "clicker_tg_id": query.from_user.id,
                "chat_message_id": chat_message_id,
                "actual_owner_tutor_id": inbound.tutor_id,
                "reason": "cross_tenant",
            },
        )
        await query.answer("Это не ваша задача.")
        return
    if inbound.business_connection_id is None or inbound.student_id is None:
        await query.answer("Недостаточно данных для ответа.")
        return

    # Defence-in-depth: only fetch the student scoped to the owning tutor.
    student_stmt = select(Student).where(
        Student.id == inbound.student_id, Student.tutor_id == clicker.id
    )
    student = (await session.execute(student_stmt)).scalar_one_or_none()
    if student is None:
        await query.answer("Ученик не найден.")
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

    if query.bot is not None:
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
