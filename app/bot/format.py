"""Pure formatters for tutor-facing messages.

Kept separate from handlers so they're trivially unit-testable.
"""
from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

from app.db.models import Lesson, Student


def format_today_message(
    rows: list[tuple[Lesson, Student]], *, date_local: date, tz_name: str
) -> str:
    if not rows:
        return f"Сегодня ({date_local.isoformat()}) уроков нет."
    tz = ZoneInfo(tz_name)
    lines = [f"Сегодня ({date_local.isoformat()}):"]
    for lesson, student in rows:
        local_time = lesson.scheduled_at.astimezone(tz).strftime("%H:%M")
        name = student.name or f"ученик #{student.id}"
        suffix = "" if lesson.status == "scheduled" else f" [{lesson.status}]"
        lines.append(f"• {local_time} — {name}{suffix}")
    return "\n".join(lines)
