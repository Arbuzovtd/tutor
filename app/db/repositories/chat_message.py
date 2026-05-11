"""Repository for ChatMessage — inbound/outbound messages with idempotency."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChatMessage


class ChatMessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def exists_by_telegram_msg(
        self, business_connection_id: str, telegram_message_id: int
    ) -> bool:
        stmt = select(ChatMessage.id).where(
            ChatMessage.business_connection_id == business_connection_id,
            ChatMessage.telegram_message_id == telegram_message_id,
        )
        result = await self.session.execute(stmt)
        return result.first() is not None

    async def record_inbound(
        self,
        *,
        tutor_id: int,
        business_connection_id: str,
        telegram_message_id: int,
        text: str,
        student_id: int | None = None,
    ) -> ChatMessage:
        msg = ChatMessage(
            tutor_id=tutor_id,
            student_id=student_id,
            business_connection_id=business_connection_id,
            direction="inbound",
            telegram_message_id=telegram_message_id,
            text=text,
        )
        self.session.add(msg)
        await self.session.flush()
        return msg

    async def last_tutor_outbound_at(
        self, business_connection_id: str
    ) -> datetime | None:
        """Latest received_at where direction='outbound_tutor', or None."""
        stmt = (
            select(ChatMessage.received_at)
            .where(
                ChatMessage.business_connection_id == business_connection_id,
                ChatMessage.direction == "outbound_tutor",
            )
            .order_by(ChatMessage.received_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def record_outbound(
        self,
        *,
        tutor_id: int,
        business_connection_id: str,
        text: str,
        direction: str = "outbound_bot",
        telegram_message_id: int | None = None,
        student_id: int | None = None,
        intent: str | None = None,
        confidence: float | None = None,
    ) -> ChatMessage:
        msg = ChatMessage(
            tutor_id=tutor_id,
            student_id=student_id,
            business_connection_id=business_connection_id,
            direction=direction,
            telegram_message_id=telegram_message_id,
            text=text,
            intent=intent,
            confidence=confidence,
        )
        self.session.add(msg)
        await self.session.flush()
        return msg
