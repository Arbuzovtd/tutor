"""IntentParser tests — uses a fake CompleterProtocol so no real OpenAI call is made."""
from __future__ import annotations

from datetime import datetime

import pytest

from app.ai.intent import IntentParser
from app.ai.types import IntentKind


class FakeCompleter:
    def __init__(self, response: str, *, raise_exc: Exception | None = None) -> None:
        self.response = response
        self.raise_exc = raise_exc
        self.calls: list[tuple[str, str]] = []

    async def complete_json(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.response


NOW = datetime(2026, 5, 11, 10, 0, 0)


async def test_prefilter_short_circuits_for_greeting():
    fake = FakeCompleter(response="{}")
    parser = IntentParser(fake)
    result = await parser.parse("привет", NOW)
    assert result.kind == IntentKind.UNKNOWN
    assert result.confidence == 1.0
    assert fake.calls == [], "GPT should not be called for non-scheduling messages"


async def test_reschedule_happy_path():
    fake = FakeCompleter(
        response='{"kind": "reschedule", "confidence": 0.92, '
        '"target_datetime": "2026-05-13T17:00:00", '
        '"new_datetime": "2026-05-15T17:00:00", '
        '"explanation": "user moves Wednesday lesson to Friday"}'
    )
    parser = IntentParser(fake)
    result = await parser.parse("можно перенести среду 17:00 на пятницу?", NOW)
    assert result.kind == IntentKind.RESCHEDULE
    assert result.confidence == pytest.approx(0.92)
    assert result.target_datetime == datetime(2026, 5, 13, 17, 0)
    assert result.new_datetime == datetime(2026, 5, 15, 17, 0)
    assert len(fake.calls) == 1


async def test_cancel_no_new_datetime():
    fake = FakeCompleter(
        response='{"kind": "cancel", "confidence": 0.85, '
        '"target_datetime": "2026-05-12T17:00:00", '
        '"new_datetime": null, "explanation": "tomorrow lesson cancelled"}'
    )
    parser = IntentParser(fake)
    result = await parser.parse("болею, отменим завтра", NOW)
    assert result.kind == IntentKind.CANCEL
    assert result.target_datetime == datetime(2026, 5, 12, 17, 0)
    assert result.new_datetime is None


async def test_invalid_json_falls_back_to_unknown():
    fake = FakeCompleter(response="not json at all")
    parser = IntentParser(fake)
    result = await parser.parse("перенесите урок", NOW)
    assert result.kind == IntentKind.UNKNOWN
    assert result.confidence == 0.0
    assert result.explanation is not None
    assert "json" in result.explanation.lower()


async def test_completer_exception_falls_back_to_unknown():
    fake = FakeCompleter(response="", raise_exc=RuntimeError("API down"))
    parser = IntentParser(fake)
    result = await parser.parse("перенесите урок", NOW)
    assert result.kind == IntentKind.UNKNOWN
    assert result.confidence == 0.0
    assert "API down" in (result.explanation or "")


async def test_unknown_kind_in_response_normalized():
    fake = FakeCompleter(
        response='{"kind": "wat", "confidence": 0.5, "explanation": "x"}'
    )
    parser = IntentParser(fake)
    result = await parser.parse("перенесите урок", NOW)
    assert result.kind == IntentKind.UNKNOWN
