"""Repository for Lesson — scheduled tutoring sessions linked to calendar events."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Lesson


class LessonRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        tutor_id: int,
        student_id: int,
        scheduled_at: datetime,
        duration_min: int = 60,
        calendar_event_id: str | None = None,
        status: str = "scheduled",
    ) -> Lesson:
        lesson = Lesson(
            tutor_id=tutor_id,
            student_id=student_id,
            scheduled_at=scheduled_at,
            duration_min=duration_min,
            calendar_event_id=calendar_event_id,
            status=status,
        )
        self.session.add(lesson)
        await self.session.flush()
        return lesson

    async def get_by_calendar_event_id(self, calendar_event_id: str) -> Lesson | None:
        stmt = select(Lesson).where(Lesson.calendar_event_id == calendar_event_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_upcoming_for_student(
        self, student_id: int, now: datetime
    ) -> list[Lesson]:
        stmt = (
            select(Lesson)
            .where(Lesson.student_id == student_id, Lesson.scheduled_at > now)
            .order_by(Lesson.scheduled_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(self, lesson_id: int, status: str) -> Lesson | None:
        lesson = await self.session.get(Lesson, lesson_id)
        if lesson is None:
            return None
        lesson.status = status
        await self.session.flush()
        return lesson
