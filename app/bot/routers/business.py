"""Handlers for Telegram Business updates: business_connection and business_message.

business_connection: persist tutor + connection so business_message handlers can
resolve them.

business_message: do null/idempotency-ish guards, then push to InboundDebouncer.
When a sender's burst quiets down (default 4s), the debouncer calls
`process_message_burst` which runs the reschedule engine and sends Telegram replies.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import Bot, Router
from aiogram.types import BusinessConnection, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.routers.review import build_review_keyboard
from app.db.repositories.business_connection import BusinessConnectionRepository
from app.db.repositories.tutor import TutorRepository
from app.services.debouncer import InboundDebouncer
from app.services.reschedule import IntentParserProtocol, handle_business_message

log = logging.getLogger(__name__)
router = Router(name="business")


@router.business_connection()
async def on_business_connection(event: BusinessConnection, session: AsyncSession) -> None:
    """Tutor connected/disconnected the bot or changed permissions in Telegram Business."""
    tutor, created = await TutorRepository(session).get_or_create(tg_user_id=event.user.id)
    if created:
        log.info(
            "Created new tutor record id=%s for telegram_user_id=%s (unregistered)",
            tutor.id,
            event.user.id,
        )

    bc = await BusinessConnectionRepository(session).upsert(
        tutor_id=tutor.id,
        connection_id=event.id,
        user_chat_id=event.user_chat_id,
        is_enabled=event.is_enabled,
        can_reply=getattr(event, "can_reply", True),
    )
    log.info(
        "business_connection upserted: id=%s tutor_id=%s registered=%s enabled=%s can_reply=%s",
        bc.connection_id,
        bc.tutor_id,
        tutor.is_registered,
        bc.is_enabled,
        bc.can_reply,
    )


@router.business_message()
async def on_business_message(
    message: Message,
    debouncer: InboundDebouncer,
) -> None:
    """Push the inbound message onto the per-sender debouncer."""
    if (
        message.business_connection_id is None
        or message.text is None
        or message.from_user is None
    ):
        return

    await debouncer.submit(
        connection_id=message.business_connection_id,
        sender_id=message.from_user.id,
        chat_id=message.chat.id,
        telegram_message_id=message.message_id,
        text=message.text,
    )


async def process_message_burst(
    *,
    bot: Bot,
    session_factory: async_sessionmaker,
    parser: IntentParserProtocol | None,
    connection_id: str,
    sender_id: int,
    chat_id: int,
    telegram_message_id: int,
    text: str,
) -> None:
    """Called by InboundDebouncer when a sender's burst quiets down.

    Opens its own session because the debouncer fires outside any aiogram
    update lifecycle — the original DbSessionMiddleware session is long gone.
    """
    async with session_factory() as session:
        try:
            result = await handle_business_message(
                session=session,
                connection_id=connection_id,
                telegram_message_id=telegram_message_id,
                from_user_id=sender_id,
                chat_id=chat_id,
                text=text,
                now=datetime.now(timezone.utc),
                parser=parser,
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    log.info(
        "burst processed: connection=%s last_msg=%s action=%s reply=%s",
        connection_id,
        telegram_message_id,
        result.action,
        bool(result.reply_text),
    )

    if result.reply_text is not None:
        try:
            await bot.send_message(
                chat_id=chat_id,
                business_connection_id=connection_id,
                text=result.reply_text,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("could not send student ack: %s", exc)

    if result.tutor_notification is not None:
        try:
            await bot.send_message(
                chat_id=result.tutor_notification.tutor_telegram_id,
                text=result.tutor_notification.text,
                reply_markup=build_review_keyboard(
                    result.tutor_notification.chat_message_id
                ),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "could not ping tutor tg_id=%s: %s",
                result.tutor_notification.tutor_telegram_id,
                exc,
            )
