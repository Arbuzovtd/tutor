"""FSM-driven onboarding: subjects → grades → working hours → price → done.

Collected profile is logged to AuditLog on completion. Storing into structured
Tutor columns is deferred — we don't yet know the exact shape we need.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.states import Onboarding
from app.db.models import AuditLog, Tutor
from sqlalchemy import select, update

log = logging.getLogger(__name__)
router = Router(name="onboarding")

# Same scoping as tutor_cmds: only direct private chats with the bot.
router.message.filter(F.chat.type == "private", F.business_connection_id.is_(None))


@router.message(Onboarding.waiting_subjects)
async def onb_subjects(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Напиши предметы текстом, например: «математика, физика».")
        return
    await state.update_data(subjects=message.text.strip())
    await state.set_state(Onboarding.waiting_grades)
    await message.answer("Какие классы? Например: «9–11» или «5, 6, 7».")


@router.message(Onboarding.waiting_grades)
async def onb_grades(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Напиши классы текстом, например: «9–11».")
        return
    await state.update_data(grades=message.text.strip())
    await state.set_state(Onboarding.waiting_working_hours)
    await message.answer(
        "В какие часы и дни ты обычно проводишь уроки? "
        "Например: «пн-пт 14:00-20:00, сб 11:00-15:00»."
    )


@router.message(Onboarding.waiting_working_hours)
async def onb_hours(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Напиши рабочие часы текстом.")
        return
    await state.update_data(working_hours=message.text.strip())
    await state.set_state(Onboarding.waiting_price)
    await message.answer("Сколько стоит один урок? Можно числом, например: «2500₽» или «$30».")


@router.message(Onboarding.waiting_price)
async def onb_price(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not message.text or message.from_user is None:
        return
    await state.update_data(price=message.text.strip())
    profile = await state.get_data()
    await state.clear()

    # Persist: mark onboarding info_collected and write a snapshot to audit log.
    result = await session.execute(
        select(Tutor).where(Tutor.telegram_user_id == message.from_user.id)
    )
    tutor = result.scalar_one_or_none()
    if tutor is None:
        log.warning("onboarding completed but no Tutor row for user %s", message.from_user.id)
        return

    await session.execute(
        update(Tutor)
        .where(Tutor.id == tutor.id)
        .values(onboarding_status="info_collected", is_registered=True)
    )
    session.add(
        AuditLog(
            tutor_id=tutor.id,
            action="onboarding_completed",
            payload_json=profile,
        )
    )
    log.info("Onboarding completed for tutor_id=%s: %s", tutor.id, profile)

    await message.answer(
        "Записал.\n\n"
        f"• Предметы: {profile.get('subjects')}\n"
        f"• Классы: {profile.get('grades')}\n"
        f"• Часы: {profile.get('working_hours')}\n"
        f"• Цена: {profile.get('price')}\n\n"
        "Следующий шаг — подключить меня к твоему Telegram Business:\n"
        "1. @BotFather → /mybots → (этот бот) → Bot Settings → Business Mode → Turn On\n"
        "2. На своём Premium-аккаунте: Settings → Telegram Business → Chatbots → впиши username этого бота\n\n"
        "Когда подключишь — я узнаю автоматически и напишу сюда."
    )
