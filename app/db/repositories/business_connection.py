"""Repository for BusinessConnection — Telegram link between bot and tutor's Premium account."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BusinessConnection


class BusinessConnectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_connection_id(self, connection_id: str) -> BusinessConnection | None:
        stmt = select(BusinessConnection).where(BusinessConnection.connection_id == connection_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(
        self,
        tutor_id: int,
        connection_id: str,
        user_chat_id: int,
        is_enabled: bool,
        can_reply: bool,
    ) -> BusinessConnection:
        existing = await self.get_by_connection_id(connection_id)
        if existing is not None:
            existing.tutor_id = tutor_id
            existing.user_chat_id = user_chat_id
            existing.is_enabled = is_enabled
            existing.can_reply = can_reply
            await self.session.flush()
            return existing
        new = BusinessConnection(
            tutor_id=tutor_id,
            connection_id=connection_id,
            user_chat_id=user_chat_id,
            is_enabled=is_enabled,
            can_reply=can_reply,
        )
        self.session.add(new)
        await self.session.flush()
        return new
