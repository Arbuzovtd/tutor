"""Phase 0 — Telegram Business Mode spike.

Goal: prove that aiogram 3.x receives business_connection / business_message
updates and can reply on behalf of the connected business account using
business_connection_id.

Run:
    cp .env.example .env
    # paste TELEGRAM_BOT_TOKEN from @BotFather into .env
    uv run python -m spike.bot
"""
from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import BusinessConnection, Message
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("spike")

router = Router(name="spike")

# Updates we explicitly need from Telegram. Business updates are NOT included
# by default in long-polling — must be requested.
ALLOWED_UPDATES = [
    "message",
    "edited_message",
    "business_connection",
    "business_message",
    "edited_business_message",
    "deleted_business_messages",
]


@router.business_connection()
async def on_business_connection(event: BusinessConnection) -> None:
    log.info(
        "business_connection: id=%s user_id=%s user_chat_id=%s "
        "is_enabled=%s can_reply=%s",
        event.id,
        event.user.id,
        event.user_chat_id,
        event.is_enabled,
        getattr(event, "can_reply", None),
    )


@router.business_message()
async def on_business_message(message: Message) -> None:
    log.info(
        "business_message: chat_id=%s from_user=%s connection_id=%s text=%r",
        message.chat.id,
        message.from_user.id if message.from_user else None,
        message.business_connection_id,
        message.text,
    )
    if not message.text:
        return
    await message.bot.send_message(
        chat_id=message.chat.id,
        business_connection_id=message.business_connection_id,
        text=f"[spike] received: {message.text}",
    )


@router.message(CommandStart())
async def on_direct_start(message: Message) -> None:
    """Direct chat with the bot owner — proves bot is alive."""
    log.info("Direct /start from user_id=%s", message.from_user.id if message.from_user else None)
    await message.answer(
        "Spike-bot is alive.\n\n"
        "Next step: enable Business Mode for me in @BotFather, then connect me "
        "in Settings → Telegram Business → Chatbots."
    )


@router.message()
async def on_direct_any(message: Message) -> None:
    """Catch-all for direct messages so we can see them in the logs."""
    log.info("direct message from %s: %r", message.from_user.id if message.from_user else None, message.text)


async def main() -> None:
    load_dotenv()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN not set. See .env.example.")

    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)

    me = await bot.get_me()
    log.info(
        "Spike bot @%s (id=%s) starting via long-polling. Allowed updates: %s",
        me.username,
        me.id,
        ALLOWED_UPDATES,
    )
    await dp.start_polling(bot, allowed_updates=ALLOWED_UPDATES)


if __name__ == "__main__":
    asyncio.run(main())
