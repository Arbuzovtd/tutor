"""GoogleCalendarBackend — implements CalendarBackend against the Google Calendar API.

Wired in Phase 3 (full OAuth flow) once GOOGLE_CLIENT_ID/SECRET are provisioned
in Google Cloud Console. Until then this module is intentionally a stub: the
in-memory backend covers Phase 5 engine work.
"""
from __future__ import annotations

from datetime import datetime

from app.calendar.base import CalendarEvent


class GoogleCalendarBackend:
    """Stub. Phase 3 will replace each NotImplementedError with a real call."""

    def __init__(self, access_token: str, calendar_id: str = "primary") -> None:
        self.access_token = access_token
        self.calendar_id = calendar_id

    async def list_events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        raise NotImplementedError("GoogleCalendarBackend pending OAuth provisioning")

    async def create_event(self, event: CalendarEvent) -> CalendarEvent:
        raise NotImplementedError("GoogleCalendarBackend pending OAuth provisioning")

    async def update_event(self, event_id: str, event: CalendarEvent) -> CalendarEvent:
        raise NotImplementedError("GoogleCalendarBackend pending OAuth provisioning")

    async def delete_event(self, event_id: str) -> None:
        raise NotImplementedError("GoogleCalendarBackend pending OAuth provisioning")

    async def find_free_slot(
        self,
        candidate_starts: list[datetime],
        duration_minutes: int,
    ) -> datetime | None:
        raise NotImplementedError("GoogleCalendarBackend pending OAuth provisioning")
