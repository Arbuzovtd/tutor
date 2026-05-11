"""Factories for runtime dependencies injected into bot handlers.

`build_intent_parser` returns None when OPENAI_API_KEY is unset — the engine
treats `parser=None` as "I'll log inbound but won't auto-reply". This lets the
bot run in dev without paying for API calls.
"""
from __future__ import annotations

import logging

from openai import AsyncOpenAI

from app.ai.client import OpenAICompleter
from app.ai.intent import IntentParser
from app.config import Settings, get_settings

log = logging.getLogger(__name__)


def build_intent_parser(settings: Settings | None = None) -> IntentParser | None:
    settings = settings or get_settings()
    if settings.openai_api_key is None:
        log.info("OPENAI_API_KEY not configured — running without intent parser")
        return None
    client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())
    return IntentParser(OpenAICompleter(client=client, model=settings.openai_model))
