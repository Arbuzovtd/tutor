"""TDD tests for InMemoryCalendar — drives the Phase 5 engine in unit tests."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.calendar.base import CalendarEvent
from app.calendar.inmemory import InMemoryCalendar


def _evt(start_h: int, end_h: int, *, summary: str = "lesson") -> CalendarEvent:
    base = datetime(2026, 5, 11, 0, 0, tzinfo=timezone.utc)
    return CalendarEvent(
        id=None,
        summary=summary,
        start=base + timedelta(hours=start_h),
        end=base + timedelta(hours=end_h),
    )


@pytest.fixture
def calendar() -> InMemoryCalendar:
    return InMemoryCalendar()


async def test_create_assigns_id(calendar: InMemoryCalendar):
    created = await calendar.create_event(_evt(10, 11))
    assert created.id is not None
    assert created.summary == "lesson"


async def test_list_events_returns_overlapping(calendar: InMemoryCalendar):
    await calendar.create_event(_evt(10, 11))
    await calendar.create_event(_evt(14, 15))
    events = await calendar.list_events(_evt(13, 16).start, _evt(13, 16).end)
    assert len(events) == 1
    assert events[0].start.hour == 14


async def test_update_replaces_content(calendar: InMemoryCalendar):
    e = await calendar.create_event(_evt(10, 11))
    new = replace(e, summary="renamed")
    updated = await calendar.update_event(e.id, new)
    assert updated.summary == "renamed"
    assert updated.id == e.id


async def test_delete_removes(calendar: InMemoryCalendar):
    e = await calendar.create_event(_evt(10, 11))
    await calendar.delete_event(e.id)
    events = await calendar.list_events(e.start, e.end + timedelta(hours=1))
    assert events == []


async def test_find_free_slot_returns_first_open(calendar: InMemoryCalendar):
    await calendar.create_event(_evt(10, 11))  # busy 10–11
    candidates = [
        datetime(2026, 5, 11, 10, 0, tzinfo=timezone.utc),  # busy
        datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc),  # free
        datetime(2026, 5, 11, 14, 0, tzinfo=timezone.utc),
    ]
    slot = await calendar.find_free_slot(candidates, duration_minutes=60)
    assert slot is not None
    assert slot.hour == 12


async def test_find_free_slot_returns_none_when_all_busy(calendar: InMemoryCalendar):
    for h in range(8, 22):
        await calendar.create_event(_evt(h, h + 1))
    candidates = [datetime(2026, 5, 11, h, 0, tzinfo=timezone.utc) for h in range(8, 22)]
    slot = await calendar.find_free_slot(candidates, duration_minutes=60)
    assert slot is None
