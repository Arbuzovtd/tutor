"""FastAPI entry point. Starts long-polling bot in the same process for dev.

For prod (Phase 10) we'll switch to webhook + a separate worker; for now a
single uvicorn process owns both the HTTP API and the polling loop.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.bot.dispatcher import ALLOWED_UPDATES, BOT_COMMANDS, make_bot, make_dispatcher
from app.config import get_settings
from app.db.session import engine
from app.services.scheduler import make_scheduler

logging.basicConfig(
    level=getattr(logging, get_settings().log_level),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    bot = make_bot()
    dp, debouncer = make_dispatcher(bot)
    me = await bot.get_me()
    log.info("Starting bot @%s (id=%s); allowed_updates=%s", me.username, me.id, ALLOWED_UPDATES)

    # Publish the command list so Telegram shows them in the "/" autocomplete.
    try:
        await bot.set_my_commands(BOT_COMMANDS)
        log.info("Published %d bot commands to Telegram", len(BOT_COMMANDS))
    except Exception as exc:  # noqa: BLE001
        log.warning("set_my_commands failed: %s", exc)

    polling_task = asyncio.create_task(
        dp.start_polling(bot, allowed_updates=ALLOWED_UPDATES, handle_signals=False),
        name="bot-polling",
    )

    scheduler = make_scheduler(bot)
    scheduler.start()
    log.info("Morning summary scheduler started (cron */1 min UTC, fires at 09:00 local per tutor)")

    try:
        yield
    finally:
        log.info("Stopping bot polling and scheduler")
        scheduler.shutdown(wait=False)
        # Drain any pending debounced bursts so we don't lose buffered text
        try:
            await debouncer.flush_all()
        except Exception as exc:  # noqa: BLE001
            log.warning("debouncer flush failed during shutdown: %s", exc)
        await dp.stop_polling()
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
        await bot.session.close()
        await engine.dispose()


app = FastAPI(title="TutorBot", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ready"}
