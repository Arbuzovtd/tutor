"""In-memory rate limiter for incoming Telegram updates.

Two independent token buckets:
- per Telegram user (any chat) — blunt DoS guard, e.g. 30 events / 60s
- per (business_connection_id, sender_id) — prevents one chatty student from
  triggering parser/LLM bursts on a single tutor's account: 10 events / 60s

If a bucket overflows, the middleware short-circuits the handler. The event
is silently dropped (we do NOT send rate-limit replies to the student — that
would be DM-style noise on the tutor's account).

In-memory state: a dict keyed by the bucket identity. Lives in the same
process as the bot polling task. For multi-process scale-up this needs Redis,
but for the MVP a single-process bot is the deployment target.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

log = logging.getLogger(__name__)


# (events, window_seconds)
USER_BUCKET = (30, 60)
BUSINESS_PER_SENDER_BUCKET = (10, 60)


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        # key -> deque of monotonic timestamps within the window
        self._user_buckets: dict[int, deque[float]] = defaultdict(deque)
        self._business_buckets: dict[tuple[str, int], deque[float]] = defaultdict(deque)

    def _allow(
        self, bucket: deque[float], *, limit: int, window: float, now: float
    ) -> bool:
        # Drop timestamps older than the window.
        cutoff = now - window
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Unwrap the inner message/callback from the Update if present.
        inner: Message | CallbackQuery | None = None
        if isinstance(event, Update):
            inner = event.message or event.business_message or event.callback_query
        elif isinstance(event, (Message, CallbackQuery)):
            inner = event

        if inner is None or inner.from_user is None:
            return await handler(event, data)

        now = time.monotonic()
        user_id = inner.from_user.id

        if not self._allow(
            self._user_buckets[user_id],
            limit=USER_BUCKET[0],
            window=USER_BUCKET[1],
            now=now,
        ):
            log.warning("rate-limit drop: user tg_id=%s exceeded user bucket", user_id)
            return None

        if isinstance(inner, Message) and inner.business_connection_id is not None:
            key = (inner.business_connection_id, user_id)
            if not self._allow(
                self._business_buckets[key],
                limit=BUSINESS_PER_SENDER_BUCKET[0],
                window=BUSINESS_PER_SENDER_BUCKET[1],
                now=now,
            ):
                log.warning(
                    "rate-limit drop: business sender tg_id=%s conn=%s",
                    user_id,
                    inner.business_connection_id,
                )
                return None

        return await handler(event, data)
