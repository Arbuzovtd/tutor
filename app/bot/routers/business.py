"""Handlers for Telegram Business updates: business_connection and business_message.

These run when a Premium-connected tutor account either toggles bot permissions
(business_connection) or receives a message from one of their chats (business_message).
"""
from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import BusinessConnection, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChatMessage, Tutor
from app.db.repositories.business_connection import BusinessConnectionRepository
from app.db.repositories.tutor import TutorRepository

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
async def on_business_message(message: Message, session: AsyncSession) -> None:
    """A message was sent to the tutor's account from a student chat.

    Phase 2 scope: log the inbound message and ack with a placeholder reply so
    we have visibility end-to-end. The decision engine is Phase 5.
    """
    if message.business_connection_id is None:
        return

    bc = await BusinessConnectionRepository(session).get_by_connection_id(
        message.business_connection_id
    )
    if bc is None:
        log.warning("business_message for unknown connection_id=%s", message.business_connection_id)
        return

    tutor = await session.get(Tutor, bc.tutor_id)
    if tutor is None or not tutor.is_registered or not tutor.is_active:
        # Auth gate: only respond for tutors who've finished /start onboarding
        # and are not suspended. We still log inbound to chat_messages for audit.
        log.info(
            "business_message ignored — tutor not registered/active "
            "(tutor_id=%s registered=%s active=%s)",
            bc.tutor_id,
            tutor.is_registered if tutor else None,
            tutor.is_active if tutor else None,
        )
        session.add(
            ChatMessage(
                tutor_id=bc.tutor_id,
                business_connection_id=message.business_connection_id,
                direction="inbound_ignored",
                telegram_message_id=message.message_id,
                text=message.text,
            )
        )
        return

    # Idempotent insert: if we've seen this telegram_message_id under this
    # connection before, the unique constraint will block a duplicate.
    session.add(
        ChatMessage(
            tutor_id=bc.tutor_id,
            business_connection_id=message.business_connection_id,
            direction="inbound",
            telegram_message_id=message.message_id,
            text=message.text,
        )
    )
    log.info(
        "business_message logged: tutor_id=%s chat_id=%s text=%r",
        bc.tutor_id,
        message.chat.id,
        message.text,
    )

    if not message.text:
        return

    # Phase 2 placeholder reply — replaced by reschedule engine in Phase 5.
    await message.bot.send_message(
        chat_id=message.chat.id,
        business_connection_id=message.business_connection_id,
        text="(Message received — full automation coming in Phase 5)",
    )
