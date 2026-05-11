"""Repository for Lesson — scheduled tutoring sessions linked to calendar events."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Lesson, Student


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

    async def list_for_tutor_on_date(
        self, *, tutor_id: int, date_local: date, tz_name: str
    ) -> list[tuple[Lesson, Student]]:
        """Lessons whose scheduled_at falls on `date_local` in timezone `tz_name`.

        Returns pairs (lesson, student) so the caller can show student names
        without an N+1 follow-up.
        """
        tz = ZoneInfo(tz_name)
        start_local = datetime.combine(date_local, time.min, tzinfo=tz)
        end_local = start_local + timedelta(days=1)
        stmt = (
            select(Lesson, Student)
            .join(Student, Lesson.student_id == Student.id)
            .where(
                Lesson.tutor_id == tutor_id,
                Lesson.scheduled_at >= start_local,
                Lesson.scheduled_at < end_local,
            )
            .order_by(Lesson.scheduled_at.asc())
        )
        result = await self.session.execute(stmt)
        return [(lesson, student) for lesson, student in result.all()]

    async def update_status(self, lesson_id: int, status: str) -> Lesson | None:
        lesson = await self.session.get(Lesson, lesson_id)
        if lesson is None:
            return None
        lesson.status = status
        await self.session.flush()
        return lesson
