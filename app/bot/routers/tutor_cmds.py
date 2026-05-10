"""Direct commands the tutor sends to the bot in their personal chat with it."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.states import Onboarding
from app.db.repositories.tutor import TutorRepository

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
        "/help — эта справка\n"
        "/cancel — прервать текущий шаг настройки"
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current is None:
        await message.answer("Нечего отменять.")
        return
    await state.clear()
    await message.answer("Текущий шаг отменён. /start чтобы начать заново.")
