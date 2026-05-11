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


def format_students_message(students: list[Student]) -> str:
    if not students:
        return "Учеников пока нет. Они появятся после первых сообщений в Business-чатах."
    lines = [f"Ученики ({len(students)}):"]
    for s in students:
        name = s.name or f"ученик #{s.id}"
        meta_parts = [p for p in (s.subject, s.grade) if p]
        meta = f" — {', '.join(meta_parts)}" if meta_parts else ""
        lines.append(f"• {name}{meta}")
    return "\n".join(lines)


def format_lessons_message(
    rows: list[tuple[Lesson, Student]], *, tz_name: str
) -> str:
    if not rows:
        return "Будущих уроков нет."
    tz = ZoneInfo(tz_name)
    lines = [f"Ближайшие уроки ({len(rows)}):"]
    for lesson, student in rows:
        local = lesson.scheduled_at.astimezone(tz)
        when = local.strftime("%d.%m %H:%M")
        name = student.name or f"ученик #{student.id}"
        suffix = "" if lesson.status == "scheduled" else f" [{lesson.status}]"
        lines.append(f"• {when} — {name}{suffix}")
    return "\n".join(lines)
