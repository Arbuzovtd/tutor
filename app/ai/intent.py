"""Intent parser: pre-filter → GPT-4o JSON-mode → typed IntentResult."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Protocol

from app.ai.prefilter import is_scheduling_message
from app.ai.prompts import INTENT_SYSTEM_PROMPT, INTENT_USER_TEMPLATE
from app.ai.types import IntentKind, IntentResult

log = logging.getLogger(__name__)


class CompleterProtocol(Protocol):
    """Minimal interface over OpenAI chat completion. Let tests inject a fake."""

    async def complete_json(self, system: str, user: str) -> str:
        """Return the assistant's content as a JSON string."""
        ...


class IntentParser:
    def __init__(self, completer: CompleterProtocol) -> None:
        self.completer = completer

    async def parse(self, text: str, current_datetime: datetime) -> IntentResult:
        if not is_scheduling_message(text):
            return IntentResult(
                kind=IntentKind.UNKNOWN,
                confidence=1.0,
                raw_text=text,
                explanation="prefilter: no scheduling indicators",
            )

        user = INTENT_USER_TEMPLATE.format(
            current_datetime=current_datetime.isoformat(),
            message=text,
        )
        try:
            content = await self.completer.complete_json(INTENT_SYSTEM_PROMPT, user)
        except Exception as exc:
            log.warning("intent completion failed: %s", exc)
            return IntentResult(
                kind=IntentKind.UNKNOWN,
                confidence=0.0,
                raw_text=text,
                explanation=f"completion error: {exc}",
            )

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            log.warning("intent JSON parse failed for content=%r: %s", content, exc)
            return IntentResult(
                kind=IntentKind.UNKNOWN,
                confidence=0.0,
                raw_text=text,
                explanation=f"json error: {exc}",
            )

        try:
            return IntentResult(
                kind=IntentKind(parsed.get("kind", "unknown")),
                confidence=float(parsed.get("confidence", 0.0)),
                target_datetime=_parse_dt(parsed.get("target_datetime")),
                new_datetime=_parse_dt(parsed.get("new_datetime")),
                raw_text=text,
                explanation=parsed.get("explanation"),
            )
        except (ValueError, TypeError) as exc:
            log.warning("intent shape invalid for parsed=%r: %s", parsed, exc)
            return IntentResult(
                kind=IntentKind.UNKNOWN,
                confidence=0.0,
                raw_text=text,
                explanation=f"shape error: {exc}",
            )


def _parse_dt(raw: str | None) -> datetime | None:
    if raw is None:
        return None
    try:
        return datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None
