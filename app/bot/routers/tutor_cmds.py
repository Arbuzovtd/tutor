"""Direct commands the tutor sends to the bot in their personal chat with it."""
from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.format import (
    format_blocks_message,
    format_lessons_message,
    format_students_message,
    format_today_message,
)
from app.bot.states import Onboarding
from app.db.repositories.audit_log import AuditLogRepository
from app.db.repositories.lesson import LessonRepository
from app.db.repositories.personal_block import PersonalBlockRepository
from app.db.repositories.student import StudentRepository
from app.db.repositories.tutor import TutorRepository
from app.services.block_parser import parse_block_args
from app.services.morning_summary import build_morning_summary

log = logging.getLogger(__name__)
router = Router(name="tutor_cmds")


# Restrict tutor commands to the bot's direct (private) chats — not business
# chats. business_message handlers cover those separately.
router.message.filter(F.chat.type == "private", F.business_connection_id.is_(None))


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if message.from_user is None:
        return
    tutor, created = await TutorRepository(session).get_or_create(tg_user_id=message.from_user.id)
    log.info("/start from tutor_id=%s (created=%s)", tutor.id, created)

    if created or tutor.onboarding_status == "started":
        await state.set_state(Onboarding.waiting_subjects)
        await message.answer(
            "Привет. Я TutorBot — буду отвечать ученикам в твоём Telegram, когда ты "
            "не можешь.\n\n"
            "Расскажи коротко о себе. Какие предметы ты ведёшь? "
            "Например: «математика, физика»."
        )
        return

    await message.answer(
        f"С возвращением. Onboarding: {tutor.onboarding_status}. "
        "Команды: /help."
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Доступные команды:\n"
        "/start — начать или возобновить настройку\n"
        "/summary — утренняя сводка (вручную)\n"
        "/today — расписание на сегодня (с личными блоками)\n"
        "/lessons — ближайшие уроки\n"
        "/students — список учеников\n"
        "/block today 14:00-15:00 обед — личный блок времени\n"
        "/blocks — все активные блоки\n"
        "/unblock N — удалить блок по id\n"
        "/help — эта справка\n"
        "/cancel — прервать текущий шаг настройки"
    )


@router.message(Command("summary"))
async def cmd_summary(message: Message, session: AsyncSession) -> None:
    """Build today's morning summary on demand."""
    if message.from_user is None:
        return
    tutor = await TutorRepository(session).get_by_telegram_user_id(message.from_user.id)
    if tutor is None:
        await message.answer("Сначала пройди регистрацию: /start")
        return
    from datetime import time, timedelta

    tz = ZoneInfo(tutor.timezone)
    today_local = datetime.now(tz).date()
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
    await message.answer(
        build_morning_summary(
            today_local=today_local,
            tz_name=tutor.timezone,
            lessons=lessons,
            blocks=blocks,
            pending_review_count=pending,
        )
    )


@router.message(Command("today"))
async def cmd_today(message: Message, session: AsyncSession) -> None:
    """Show today's lessons and personal blocks in the tutor's timezone."""
    if message.from_user is None:
        return
    tutor = await TutorRepository(session).get_by_telegram_user_id(message.from_user.id)
    if tutor is None:
        await message.answer("Сначала пройди регистрацию: /start")
        return
    tz = ZoneInfo(tutor.timezone)
    today_local = datetime.now(tz).date()
    from datetime import time, timedelta

    start_local = datetime.combine(today_local, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)

    rows = await LessonRepository(session).list_for_tutor_on_date(
        tutor_id=tutor.id, date_local=today_local, tz_name=tutor.timezone
    )
    blocks = await PersonalBlockRepository(session).list_for_tutor_in_range(
        tutor_id=tutor.id, range_start=start_local, range_end=end_local
    )
    await message.answer(
        format_today_message(
            rows, date_local=today_local, tz_name=tutor.timezone, blocks=blocks
        )
    )


@router.message(Command("block"))
async def cmd_block(message: Message, session: AsyncSession) -> None:
    """Add a personal block of time. Usage: /block today 14:00-15:00 label."""
    if message.from_user is None or message.text is None:
        return
    tutor = await TutorRepository(session).get_by_telegram_user_id(message.from_user.id)
    if tutor is None:
        await message.answer("Сначала пройди регистрацию: /start")
        return

    args = message.text.removeprefix("/block").strip()
    if not args:
        await message.answer(
            "Использование:\n"
            "/block today 14:00-15:00 обед\n"
            "/block tomorrow 09:00-10:00 встреча\n"
            "/block 2026-05-20 12:00-13:30 врач\n"
            "/block 2026-06-20 2026-06-25 каникулы"
        )
        return

    tz = ZoneInfo(tutor.timezone)
    today_local = datetime.now(tz).date()
    spec = parse_block_args(args, today_local=today_local, tz_name=tutor.timezone)
    if spec is None:
        await message.answer(
            "Не понял формат. Пример: /block today 14:00-15:00 обед"
        )
        return

    block = await PersonalBlockRepository(session).create(
        tutor_id=tutor.id,
        starts_at=spec.starts_at,
        ends_at=spec.ends_at,
        label=spec.label,
    )
    await message.answer(f"Блок #{block.id} добавлен: {spec.label or '(без названия)'}")


@router.message(Command("blocks"))
async def cmd_blocks(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    tutor = await TutorRepository(session).get_by_telegram_user_id(message.from_user.id)
    if tutor is None:
        await message.answer("Сначала пройди регистрацию: /start")
        return
    from datetime import timezone as dt_tz

    now = datetime.now(dt_tz.utc)
    blocks = await PersonalBlockRepository(session).list_upcoming_for_tutor(
        tutor_id=tutor.id, now=now
    )
    await message.answer(format_blocks_message(blocks, tz_name=tutor.timezone))


@router.message(Command("unblock"))
async def cmd_unblock(message: Message, session: AsyncSession) -> None:
    if message.from_user is None or message.text is None:
        return
    tutor = await TutorRepository(session).get_by_telegram_user_id(message.from_user.id)
    if tutor is None:
        await message.answer("Сначала пройди регистрацию: /start")
        return
    args = message.text.removeprefix("/unblock").strip()
    try:
        block_id = int(args)
    except ValueError:
        await message.answer("Использование: /unblock 5 (id из /blocks)")
        return
    ok = await PersonalBlockRepository(session).delete_by_id(
        tutor_id=tutor.id, block_id=block_id
    )
    await message.answer("Удалён." if ok else "Блок не найден.")


@router.message(Command("students"))
async def cmd_students(message: Message, session: AsyncSession) -> None:
    """Show all students for the tutor."""
    if message.from_user is None:
        return
    tutor = await TutorRepository(session).get_by_telegram_user_id(message.from_user.id)
    if tutor is None:
        await message.answer("Сначала пройди регистрацию: /start")
        return
    students = await StudentRepository(session).list_for_tutor(tutor.id)
    await message.answer(format_students_message(students))


@router.message(Command("lessons"))
async def cmd_lessons(message: Message, session: AsyncSession) -> None:
    """Show upcoming lessons in the tutor's timezone."""
    if message.from_user is None:
        return
    tutor = await TutorRepository(session).get_by_telegram_user_id(message.from_user.id)
    if tutor is None:
        await message.answer("Сначала пройди регистрацию: /start")
        return
    from datetime import timezone as dt_timezone

    now = datetime.now(dt_timezone.utc)
    rows = await LessonRepository(session).list_upcoming_for_tutor(
        tutor_id=tutor.id, now=now
    )
    await message.answer(format_lessons_message(rows, tz_name=tutor.timezone))


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current is None:
        await message.answer("Нечего отменять.")
        return
    await state.clear()
    await message.answer("Текущий шаг отменён. /start чтобы начать заново.")
