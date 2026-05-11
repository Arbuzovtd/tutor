"""Daily morning summary scheduler.

Cron-style job that runs every minute, scans all registered+active tutors,
and sends a summary to those whose local time matches DELIVERY_HOUR:DELIVERY_MINUTE.
Deduped per day via an audit_log row with action='morning_summary_sent'.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.db.models import AuditLog, Tutor
from app.db.repositories.audit_log import AuditLogRepository
from app.db.repositories.lesson import LessonRepository
from app.db.repositories.personal_block import PersonalBlockRepository
from app.db.session import AsyncSessionLocal
from app.services.morning_summary import build_morning_summary

if TYPE_CHECKING:
    from aiogram import Bot

log = logging.getLogger(__name__)

DELIVERY_HOUR = 9
DELIVERY_MINUTE = 0


async def _was_summary_sent_today(session, *, tutor_id: int, today_local: date) -> bool:
    stmt = (
        select(AuditLog.id)
        .where(
            AuditLog.tutor_id == tutor_id,
            AuditLog.action == "morning_summary_sent",
            AuditLog.payload_json["date"].astext == today_local.isoformat(),
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def _send_summary_for_tutor(bot: "Bot", session, tutor: Tutor) -> None:
    tz = ZoneInfo(tutor.timezone)
    today_local = datetime.now(tz).date()
    if await _was_summary_sent_today(session, tutor_id=tutor.id, today_local=today_local):
        return

    start_local = datetime.combine(today_local, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    lessons = await LessonRepository(session).list_for_tutor_on_date(
        tutor_id=tutor.id, date_local=today_local, tz_name=tutor.timezone
    )
    blocks = await PersonalBlockRepository(session).list_for_tutor_in_range(
        tutor_id=tutor.id, range_start=start_local, range_end=end_local
    )
    pending = await AuditLogRepository(session).count_pending_review_unresolved(
        tutor_id=tutor.id
    )
    text = build_morning_summary(
        today_local=today_local,
        tz_name=tutor.timezone,
        lessons=lessons,
        blocks=blocks,
        pending_review_count=pending,
    )

    # Claim the slot in the audit log BEFORE the Telegram send so a concurrent
    # tick (e.g., from a process restart in the same minute) is blocked by the
    # commit. Cost: if send_message fails after this point, we won't retry today
    # — that's the right trade-off (avoid duplicate spam).
    await AuditLogRepository(session).log(
        tutor_id=tutor.id,
        action="morning_summary_sent",
        payload={"date": today_local.isoformat()},
    )
    await session.commit()

    try:
        await bot.send_message(chat_id=tutor.telegram_user_id, text=text)
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "morning summary send failed tutor_id=%s tg=%s: %s (audit row already claimed)",
            tutor.id,
            tutor.telegram_user_id,
            exc,
        )


async def morning_summary_tick(bot: "Bot") -> None:
    """One scheduler tick: send summary to each tutor whose local time is 9:00.

    Uses a fresh session per tutor so a partial failure can't poison other
    tutors' work in the same iteration.
    """
    async with AsyncSessionLocal() as scan_session:
        stmt = select(Tutor).where(Tutor.is_active.is_(True), Tutor.is_registered.is_(True))
        tutors = list((await scan_session.execute(stmt)).scalars().all())

    for tutor in tutors:
        try:
            tz = ZoneInfo(tutor.timezone)
        except Exception:  # noqa: BLE001
            log.warning(
                "invalid timezone for tutor_id=%s: %r — skipping",
                tutor.id,
                tutor.timezone,
            )
            continue
        now_local = datetime.now(tz)
        if not (now_local.hour == DELIVERY_HOUR and now_local.minute == DELIVERY_MINUTE):
            continue

        async with AsyncSessionLocal() as session:
            try:
                # Re-fetch tutor inside this session so identity tracking works.
                fresh = await session.get(Tutor, tutor.id)
                if fresh is None:
                    continue
                await _send_summary_for_tutor(bot, session, fresh)
            except Exception as exc:  # noqa: BLE001
                await session.rollback()
                log.exception("morning summary failed for tutor_id=%s: %s", tutor.id, exc)


def make_scheduler(bot: "Bot") -> AsyncIOScheduler:
    sched = AsyncIOScheduler(timezone="UTC")
    sched.add_job(
        morning_summary_tick,
        trigger="cron",
        minute="*",
        kwargs={"bot": bot},
        id="morning_summary_tick",
        max_instances=1,
        coalesce=True,
    )
    return sched
