"""Pure formatters for tutor-facing messages.

Kept separate from handlers so they're trivially unit-testable.
"""
from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

from app.db.models import Lesson, PersonalBlock, Student


def format_today_message(
    rows: list[tuple[Lesson, Student]],
    *,
    date_local: date,
    tz_name: str,
    blocks: list[PersonalBlock] | None = None,
) -> str:
    blocks = blocks or []
    if not rows and not blocks:
        return f"Сегодня ({date_local.isoformat()}) пусто."
    tz = ZoneInfo(tz_name)
    lines = [f"Сегодня ({date_local.isoformat()}):"]
    for lesson, student in rows:
        local_time = lesson.scheduled_at.astimezone(tz).strftime("%H:%M")
        name = student.name or f"ученик #{student.id}"
        suffix = "" if lesson.status == "scheduled" else f" [{lesson.status}]"
        lines.append(f"• {local_time} — {name}{suffix}")
    for block in blocks:
        start = block.starts_at.astimezone(tz).strftime("%H:%M")
        end = block.ends_at.astimezone(tz).strftime("%H:%M")
        label = block.label or "блок"
        lines.append(f"🚫 {start}-{end} — {label}")
    return "\n".join(lines)


def format_blocks_message(blocks: list[PersonalBlock], *, tz_name: str) -> str:
    if not blocks:
        return "Личных блоков нет."
    tz = ZoneInfo(tz_name)
    lines = [f"Личные блоки ({len(blocks)}):"]
    for b in blocks:
        start = b.starts_at.astimezone(tz)
        end = b.ends_at.astimezone(tz)
        if start.date() == end.date() or (end - start).total_seconds() <= 24 * 3600:
            when = f"{start.strftime('%d.%m %H:%M')}–{end.strftime('%H:%M')}"
        else:
            # multi-day all-day block: end is exclusive (next day 00:00)
            from datetime import timedelta

            inclusive_end = end - timedelta(seconds=1)
            when = f"{start.strftime('%d.%m')}–{inclusive_end.strftime('%d.%m')}"
        label = b.label or "блок"
        lines.append(f"#{b.id} • {when} — {label}")
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
