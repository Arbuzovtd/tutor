"""Morning summary — text the tutor sees every day at 9:00 in their timezone.

Pure builder: given today's lessons + blocks + pending-review count, produces
a formatted message. The scheduler/dispatcher loops are orchestration concerns
elsewhere (see /summary command for manual trigger; APScheduler wiring TBD).
"""
from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

from app.db.models import Lesson, PersonalBlock, Student


def build_morning_summary(
    *,
    today_local: date,
    tz_name: str,
    lessons: list[tuple[Lesson, Student]],
    blocks: list[PersonalBlock],
    pending_review_count: int = 0,
) -> str:
    tz = ZoneInfo(tz_name)
    header = f"☀️ Доброе утро. Сегодня {today_local.isoformat()}:"

    if not lessons and not blocks and pending_review_count == 0:
        return header + "\n\nСвободный день."

    sections: list[str] = [header]

    if lessons:
        section = ["", "📚 Уроки:"]
        for lesson, student in lessons:
            local = lesson.scheduled_at.astimezone(tz).strftime("%H:%M")
            name = student.name or f"ученик #{student.id}"
            mark = "" if lesson.status == "scheduled" else f" [{lesson.status}]"
            section.append(f"  • {local} — {name}{mark}")
        sections.extend(section)

    if blocks:
        section = ["", "🚫 Личные блоки:"]
        for b in blocks:
            start = b.starts_at.astimezone(tz).strftime("%H:%M")
            end = b.ends_at.astimezone(tz).strftime("%H:%M")
            label = b.label or "блок"
            section.append(f"  • {start}-{end} — {label}")
        sections.extend(section)

    if pending_review_count > 0:
        word = "сообщение" if pending_review_count == 1 else "сообщений"
        sections.append(
            f"\n💬 Требует решения: {pending_review_count} {word}. См. /pending."
        )

    return "\n".join(sections)
