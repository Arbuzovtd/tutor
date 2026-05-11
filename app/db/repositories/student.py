"""Repository for Student — students of a tutor, isolated per tutor_id."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Student


class StudentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_tutor(self, tutor_id: int) -> list[Student]:
        """All students for a tutor, sorted by name (alphabetical, then by id for ties)."""
        stmt = (
            select(Student)
            .where(Student.tutor_id == tutor_id)
            .order_by(Student.name.asc().nulls_last(), Student.id.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_or_create_by_telegram_id(
        self,
        *,
        tutor_id: int,
        telegram_user_id: int,
        telegram_chat_id: int,
    ) -> tuple[Student, bool]:
        """Returns (student, created). `created=True` on insert, `False` on reuse."""
        stmt = select(Student).where(
            Student.tutor_id == tutor_id,
            Student.telegram_user_id == telegram_user_id,
        )
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            return existing, False
        student = Student(
            tutor_id=tutor_id,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
        )
        self.session.add(student)
        await self.session.flush()
        return student, True
