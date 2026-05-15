"""on_business_message must self-heal a missing BusinessConnection row.

When the bot misses Telegram's `business_connection` update (e.g. it was
restarting during a reconnect), the engine would forever return
`unknown_connection`. The router now compensates by pulling the connection
info via Bot.get_business_connection on the first message.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from aiogram.exceptions import TelegramAPIError

from app.bot.routers.business import on_business_message
from app.db.repositories.business_connection import BusinessConnectionRepository
from app.db.repositories.tutor import TutorRepository


class _CapturingDebouncer:
    def __init__(self) -> None:
        self.submitted: list[dict[str, Any]] = []

    async def submit(self, **kwargs: Any) -> None:
        self.submitted.append(kwargs)


class _FakeBot:
    def __init__(self, bc_info: Any | None = None, raise_exc: Exception | None = None):
        self._info = bc_info
        self._raise = raise_exc
        self.calls: list[str] = []

    async def get_business_connection(self, *, business_connection_id: str):
        self.calls.append(business_connection_id)
        if self._raise is not None:
            raise self._raise
        return self._info


def _make_message(*, conn_id: str, text: str = "hello") -> SimpleNamespace:
    return SimpleNamespace(
        business_connection_id=conn_id,
        text=text,
        from_user=SimpleNamespace(id=99999),
        chat=SimpleNamespace(id=99999),
        message_id=4242,
    )


@pytest.mark.asyncio
async def test_recovers_missing_bc_and_forwards_to_debouncer(db_session):
    conn_id = "fresh_conn_42"
    info = SimpleNamespace(
        id=conn_id,
        user=SimpleNamespace(id=777_111),
        user_chat_id=777_111,
        is_enabled=True,
        can_reply=True,
    )
    bot = _FakeBot(bc_info=info)
    deb = _CapturingDebouncer()

    await on_business_message(
        message=_make_message(conn_id=conn_id),
        debouncer=deb,
        session=db_session,
        bot=bot,
    )

    assert bot.calls == [conn_id], "Bot.get_business_connection should be hit exactly once"

    bc = await BusinessConnectionRepository(db_session).get_by_connection_id(conn_id)
    assert bc is not None
    assert bc.is_enabled is True
    assert bc.can_reply is True

    tutor = await TutorRepository(db_session).get_by_telegram_user_id(777_111)
    assert tutor is not None
    assert bc.tutor_id == tutor.id

    assert len(deb.submitted) == 1
    assert deb.submitted[0]["connection_id"] == conn_id


@pytest.mark.asyncio
async def test_existing_bc_skips_recovery_call(db_session):
    conn_id = "already_known_conn"
    tutor, _ = await TutorRepository(db_session).get_or_create(tg_user_id=555_000)
    await BusinessConnectionRepository(db_session).upsert(
        tutor_id=tutor.id,
        connection_id=conn_id,
        user_chat_id=555_000,
        is_enabled=True,
        can_reply=True,
    )
    await db_session.flush()

    bot = _FakeBot(bc_info=None)
    deb = _CapturingDebouncer()

    await on_business_message(
        message=_make_message(conn_id=conn_id),
        debouncer=deb,
        session=db_session,
        bot=bot,
    )

    assert bot.calls == [], "No Bot API hit when BC is already cached"
    assert len(deb.submitted) == 1


@pytest.mark.asyncio
async def test_recovery_failure_drops_message_silently(db_session):
    conn_id = "broken_conn"
    err = TelegramAPIError(method=object(), message="connection not found")
    bot = _FakeBot(raise_exc=err)
    deb = _CapturingDebouncer()

    await on_business_message(
        message=_make_message(conn_id=conn_id),
        debouncer=deb,
        session=db_session,
        bot=bot,
    )

    assert bot.calls == [conn_id]
    bc = await BusinessConnectionRepository(db_session).get_by_connection_id(conn_id)
    assert bc is None, "Failed recovery must not leave a half-baked BC row"
    assert deb.submitted == [], "Message must be dropped, not handed to the debouncer"
