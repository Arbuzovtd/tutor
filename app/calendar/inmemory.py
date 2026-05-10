"""In-memory CalendarBackend used by tests and dev environments without OAuth."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from app.calendar.base import CalendarEvent


class InMemoryCalendar:
    def __init__(self) -> None:
        self._events: dict[str, CalendarEvent] = {}
        self._next_id = 1

    def _new_id(self) -> str:
        i = self._next_id
        self._next_id += 1
        return f"mem-{i}"

    @staticmethod
    def _overlaps(event: CalendarEvent, start: datetime, end: datetime) -> bool:
        # Half-open interval [start, end).
        return event.end > start and event.start < end

    async def list_events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        return [e for e in self._events.values() if self._overlaps(e, start, end)]

    async def create_event(self, event: CalendarEvent) -> CalendarEvent:
        new_id = event.id or self._new_id()
        new = replace(event, id=new_id)
        self._events[new_id] = new
        return new

    async def update_event(self, event_id: str, event: CalendarEvent) -> CalendarEvent:
        new = replace(event, id=event_id)
        self._events[event_id] = new
        return new

    async def delete_event(self, event_id: str) -> None:
        self._events.pop(event_id, None)

    async def find_free_slot(
        self,
        candidate_starts: list[datetime],
        duration_minutes: int,
    ) -> datetime | None:
        delta = timedelta(minutes=duration_minutes)
        for start in candidate_starts:
            if not await self.list_events(start, start + delta):
                return start
        return None
