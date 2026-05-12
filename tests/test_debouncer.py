"""Tests for InboundDebouncer."""
from __future__ import annotations

import asyncio

import pytest

from app.services.debouncer import InboundDebouncer


@pytest.fixture
def fire_log():
    """A simple list that captures every on_fire call."""
    return []


@pytest.fixture
def make_debouncer(fire_log):
    """Factory that builds a debouncer with very short delays for tests."""
    def _build(delay: float = 0.05, max_wait: float = 0.5):
        async def on_fire(**kwargs):
            fire_log.append(kwargs)

        return InboundDebouncer(on_fire, delay=delay, max_wait=max_wait)

    return _build


async def test_single_message_fires_after_delay(make_debouncer, fire_log):
    deb = make_debouncer(delay=0.05)
    await deb.submit(
        connection_id="c1",
        sender_id=1,
        chat_id=1,
        telegram_message_id=10,
        text="привет",
    )
    await asyncio.sleep(0.12)
    assert len(fire_log) == 1
    assert fire_log[0]["text"] == "привет"
    assert fire_log[0]["telegram_message_id"] == 10


async def test_burst_is_merged_into_one_fire(make_debouncer, fire_log):
    deb = make_debouncer(delay=0.05)
    for i, chunk in enumerate(["привет", "перенеси", "на четверг"], start=1):
        await deb.submit(
            connection_id="c2",
            sender_id=2,
            chat_id=2,
            telegram_message_id=100 + i,
            text=chunk,
        )
        # Quick inter-message gap shorter than the debounce window
        await asyncio.sleep(0.02)
    await asyncio.sleep(0.12)

    assert len(fire_log) == 1
    assert fire_log[0]["text"] == "привет\nперенеси\nна четверг"
    # Last message id propagates so engine idempotency works on retries
    assert fire_log[0]["telegram_message_id"] == 103


async def test_separate_senders_dont_share_buffer(make_debouncer, fire_log):
    deb = make_debouncer(delay=0.05)
    await deb.submit(
        connection_id="c3",
        sender_id=10,
        chat_id=10,
        telegram_message_id=1,
        text="a",
    )
    await deb.submit(
        connection_id="c3",
        sender_id=20,
        chat_id=20,
        telegram_message_id=2,
        text="b",
    )
    await asyncio.sleep(0.12)
    assert len(fire_log) == 2
    texts = {f["text"] for f in fire_log}
    assert texts == {"a", "b"}


async def test_separate_connections_dont_share_buffer(make_debouncer, fire_log):
    deb = make_debouncer(delay=0.05)
    await deb.submit(
        connection_id="conn_A",
        sender_id=5,
        chat_id=5,
        telegram_message_id=1,
        text="a",
    )
    await deb.submit(
        connection_id="conn_B",
        sender_id=5,
        chat_id=5,
        telegram_message_id=2,
        text="b",
    )
    await asyncio.sleep(0.12)
    assert len(fire_log) == 2


async def test_max_wait_caps_indefinite_reset(make_debouncer, fire_log):
    """If the student keeps typing faster than the debounce, MAX_WAIT still fires."""
    deb = make_debouncer(delay=0.1, max_wait=0.2)
    # Each iteration submits before the debounce window expires,
    # but max_wait must fire around 0.2s from the first submit.
    for i in range(8):
        await deb.submit(
            connection_id="c4",
            sender_id=4,
            chat_id=4,
            telegram_message_id=200 + i,
            text=f"part{i}",
        )
        await asyncio.sleep(0.05)
    # By now total elapsed ≈ 8 * 0.05 = 0.4s > max_wait
    # The debouncer should have fired at least once already
    assert len(fire_log) >= 1
    # All submitted parts must appear somewhere in the fired payloads
    all_text = "\n".join(f["text"] for f in fire_log)
    for i in range(8):
        assert f"part{i}" in all_text


async def test_flush_all_drains_pending_buffers(make_debouncer, fire_log):
    deb = make_debouncer(delay=10.0)  # long enough to never fire on its own
    await deb.submit(
        connection_id="c5",
        sender_id=5,
        chat_id=5,
        telegram_message_id=300,
        text="буду писать дальше",
    )
    # Without flush the message would sit in the buffer forever
    await deb.flush_all()
    assert len(fire_log) == 1
    assert fire_log[0]["text"] == "буду писать дальше"
