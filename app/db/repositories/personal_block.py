"""Repository for PersonalBlock — tutor's blocked time slots (one-off, no calendar)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PersonalBlock


class PersonalBlockRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        tutor_id: int,
        starts_at: datetime,
        ends_at: datetime,
        label: str | None = None,
    ) -> PersonalBlock:
        block = PersonalBlock(
            tutor_id=tutor_id,
            starts_at=starts_at,
            ends_at=ends_at,
            label=label,
        )
        self.session.add(block)
        await self.session.flush()
        return block

    async def list_for_tutor_in_range(
        self, *, tutor_id: int, range_start: datetime, range_end: datetime
    ) -> list[PersonalBlock]:
        """Blocks overlapping [range_start, range_end). Sorted by starts_at."""
        stmt = (
            select(PersonalBlock)
            .where(
                PersonalBlock.tutor_id == tutor_id,
                PersonalBlock.ends_at > range_start,
                PersonalBlock.starts_at < range_end,
            )
            .order_by(PersonalBlock.starts_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_upcoming_for_tutor(
        self, *, tutor_id: int, now: datetime, limit: int = 50
    ) -> list[PersonalBlock]:
        stmt = (
            select(PersonalBlock)
            .where(PersonalBlock.tutor_id == tutor_id, PersonalBlock.ends_at > now)
            .order_by(PersonalBlock.starts_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_by_id(self, *, tutor_id: int, block_id: int) -> bool:
        """Delete a block if it belongs to this tutor. Returns True if deleted."""
        block = await self.session.get(PersonalBlock, block_id)
        if block is None or block.tutor_id != tutor_id:
            return False
        await self.session.delete(block)
        await self.session.flush()
        return True
