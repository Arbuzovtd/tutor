"""Abstract calendar backend — Google and (future) iCloud both implement this."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class CalendarEvent:
    id: str | None
    summary: str
    start: datetime
    end: datetime
    description: str | None = None
    is_personal_block: bool = False


class CalendarBackend(Protocol):
    """Calendar provider interface used by the reschedule engine.

    Implementations: GoogleCalendarBackend (production), InMemoryCalendar
    (tests + dev-without-OAuth), CalDavCalendarBackend (v1.1).
    """

    async def list_events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        """All events that overlap [start, end)."""
        ...

    async def create_event(self, event: CalendarEvent) -> CalendarEvent:
        """Create an event; returned event has provider-assigned id."""
        ...

    async def update_event(self, event_id: str, event: CalendarEvent) -> CalendarEvent: ...

    async def delete_event(self, event_id: str) -> None: ...

    async def find_free_slot(
        self,
        candidate_starts: list[datetime],
        duration_minutes: int,
    ) -> datetime | None:
        """Return the first candidate start that has no overlap, else None."""
        ...
