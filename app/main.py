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

from app.bot.dispatcher import ALLOWED_UPDATES, make_bot, make_dispatcher
from app.config import get_settings
from app.db.session import engine

logging.basicConfig(
    level=getattr(logging, get_settings().log_level),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    bot = make_bot()
    dp = make_dispatcher()
    me = await bot.get_me()
    log.info("Starting bot @%s (id=%s); allowed_updates=%s", me.username, me.id, ALLOWED_UPDATES)

    polling_task = asyncio.create_task(
        dp.start_polling(bot, allowed_updates=ALLOWED_UPDATES, handle_signals=False),
        name="bot-polling",
    )

    try:
        yield
    finally:
        log.info("Stopping bot polling")
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
