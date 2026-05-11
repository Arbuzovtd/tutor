"""Handlers for Telegram Business updates: business_connection and business_message.

business_connection: persist tutor + connection so business_message handlers can
resolve them.

business_message: delegate to the reschedule engine. The engine is the single
source of truth for auth gating, idempotency, handoff detection, and intent
routing — see `app/services/reschedule.py`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import Router
from aiogram.types import BusinessConnection, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.business_connection import BusinessConnectionRepository
from app.db.repositories.tutor import TutorRepository
from app.services.reschedule import IntentParserProtocol, handle_business_message

log = logging.getLogger(__name__)
router = Router(name="business")


@router.business_connection()
async def on_business_connection(event: BusinessConnection, session: AsyncSession) -> None:
    """Tutor connected/disconnected the bot or changed permissions in Telegram Business.

    We always store the connection so that when an unregistered user later
    completes /start onboarding, we already have their connection_id ready.
    But until they finish onboarding, business_message handlers ignore them.
    """
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
    session: AsyncSession,
    parser: IntentParserProtocol | None = None,
) -> None:
    """Hand off to the reschedule engine; only send a reply if engine produced one."""
    if message.business_connection_id is None or message.text is None:
        return

    result = await handle_business_message(
        session=session,
        connection_id=message.business_connection_id,
        telegram_message_id=message.message_id,
        from_user_id=message.from_user.id if message.from_user else 0,
        chat_id=message.chat.id,
        text=message.text,
        now=datetime.now(timezone.utc),
        parser=parser,
    )
    log.info(
        "business_message handled: connection=%s msg=%s action=%s reply=%s",
        message.business_connection_id,
        message.message_id,
        result.action,
        bool(result.reply_text),
    )

    if result.reply_text is not None:
        await message.bot.send_message(
            chat_id=message.chat.id,
            business_connection_id=message.business_connection_id,
            text=result.reply_text,
        )
