"""Bot + Dispatcher factory. Wires routers and the DB session middleware."""
from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.deps import build_intent_parser
from app.bot.middlewares.db import DbSessionMiddleware
from app.bot.routers import business as business_router
from app.bot.routers import onboarding as onboarding_router
from app.bot.routers import tutor_cmds as tutor_cmds_router
from app.config import get_settings
from app.db.session import AsyncSessionLocal

log = logging.getLogger(__name__)

# Updates we explicitly request from Telegram. Business updates are not
# delivered by default in long-polling.
ALLOWED_UPDATES = [
    "message",
    "edited_message",
    "callback_query",
    "business_connection",
    "business_message",
    "edited_business_message",
    "deleted_business_messages",
]


def make_bot() -> Bot:
    return Bot(
        token=get_settings().telegram_bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def make_dispatcher() -> Dispatcher:
    # Parser is shared across handlers (stateless wrapper over AsyncOpenAI).
    # None when OPENAI_API_KEY missing — engine then logs without auto-replying.
    parser = build_intent_parser()
    dp = Dispatcher(storage=MemoryStorage(), parser=parser)

    # Inject AsyncSession into every handler that asks for `session: AsyncSession`.
    # Cover both regular updates and business updates — Telegram delivers them
    # through different observers, so middleware needs registering on each.
    middleware = DbSessionMiddleware(AsyncSessionLocal)
    dp.update.outer_middleware(middleware)

    # Order matters for command/state handlers: tutor_cmds first (CommandStart
    # outranks generic FSM handlers), then onboarding state handlers, then
    # business handlers (separate update types so order is incidental there).
    dp.include_router(tutor_cmds_router.router)
    dp.include_router(onboarding_router.router)
    dp.include_router(business_router.router)

    return dp
