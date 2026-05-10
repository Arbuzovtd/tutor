"""Repository for Tutor — multi-tenant root entity."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Tutor


class TutorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_telegram_user_id(self, tg_user_id: int) -> Tutor | None:
        stmt = select(Tutor).where(Tutor.telegram_user_id == tg_user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        tg_user_id: int,
        name: str | None = None,
        timezone: str = "Europe/Moscow",
    ) -> Tutor:
        tutor = Tutor(telegram_user_id=tg_user_id, name=name, timezone=timezone)
        self.session.add(tutor)
        await self.session.flush()
        return tutor

    async def get_or_create(self, tg_user_id: int) -> tuple[Tutor, bool]:
        existing = await self.get_by_telegram_user_id(tg_user_id)
        if existing is not None:
            return existing, False
        return await self.create(tg_user_id=tg_user_id), True
