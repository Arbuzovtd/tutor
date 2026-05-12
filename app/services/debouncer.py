"""In-memory debouncer for inbound student messages.

Students often type in bursts ("привет" → "перенеси" → "на четверг"). Without
debouncing the bot would fire the LLM parser on each fragment, generate 3
acks, ping the tutor 3 times. Bad UX and 3× cost.

Per (connection_id, sender_id) we keep a buffer + a pending asyncio.Task that
sleeps for DEBOUNCE_DELAY. New messages reset the timer. When the timer fires
without interruption, we concat all buffered texts and invoke the on_fire
callback once with the merged text and the LAST telegram_message_id (so
idempotency in handle_business_message still works on retries).

A hard MAX_WAIT cap prevents a chatty student from blocking the bot forever
(if they keep sending one message every 3s, the bot still fires after 20s).
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

DEBOUNCE_DELAY = 4.0  # seconds of quiet before firing
MAX_WAIT = 20.0  # absolute cap from the first message in a burst


@dataclass
class _Pending:
    """One sender's in-flight burst."""

    chunks: list[str] = field(default_factory=list)
    last_message_id: int = 0
    chat_id: int = 0
    sender_id: int = 0
    first_arrival: float = 0.0
    task: asyncio.Task | None = None


# (connection_id, sender_telegram_id) -> burst state
_Buffers = dict[tuple[str, int], _Pending]


OnFire = Callable[..., Awaitable[None]]


class InboundDebouncer:
    def __init__(
        self,
        on_fire: OnFire,
        *,
        delay: float = DEBOUNCE_DELAY,
        max_wait: float = MAX_WAIT,
    ) -> None:
        self.on_fire = on_fire
        self.delay = delay
        self.max_wait = max_wait
        self._buffers: _Buffers = {}

    async def submit(
        self,
        *,
        connection_id: str,
        sender_id: int,
        chat_id: int,
        telegram_message_id: int,
        text: str,
    ) -> None:
        key = (connection_id, sender_id)
        now = time.monotonic()

        pending = self._buffers.get(key)
        if pending is None:
            pending = _Pending(first_arrival=now)
            self._buffers[key] = pending

        pending.chunks.append(text)
        pending.last_message_id = telegram_message_id
        pending.chat_id = chat_id
        pending.sender_id = sender_id

        if pending.task is not None and not pending.task.done():
            pending.task.cancel()

        # Decide how long to wait: normal debounce delay, but never beyond MAX_WAIT
        # from the first message of this burst.
        elapsed = now - pending.first_arrival
        wait_for = max(0.0, min(self.delay, self.max_wait - elapsed))

        pending.task = asyncio.create_task(self._wait_and_fire(key, wait_for))

    async def _wait_and_fire(self, key: tuple[str, int], wait_for: float) -> None:
        try:
            await asyncio.sleep(wait_for)
        except asyncio.CancelledError:
            return

        pending = self._buffers.pop(key, None)
        if pending is None or not pending.chunks:
            return

        merged_text = "\n".join(pending.chunks)
        try:
            await self.on_fire(
                connection_id=key[0],
                sender_id=pending.sender_id,
                chat_id=pending.chat_id,
                telegram_message_id=pending.last_message_id,
                text=merged_text,
            )
        except Exception as exc:  # noqa: BLE001
            log.exception(
                "debouncer on_fire failed for connection=%s sender=%s: %s",
                key[0],
                key[1],
                exc,
            )

    async def flush_all(self) -> None:
        """Cancel pending timers and synchronously fire any non-empty buffers.

        Intended for graceful shutdown so we don't lose buffered text.
        """
        keys = list(self._buffers.keys())
        for key in keys:
            pending = self._buffers.get(key)
            if pending is None:
                continue
            if pending.task is not None:
                pending.task.cancel()
            # Reuse _wait_and_fire with zero delay to ensure consistent semantics
            await self._wait_and_fire(key, 0.0)
