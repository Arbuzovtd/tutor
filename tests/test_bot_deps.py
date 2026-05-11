"""TDD tests for app.bot.deps.build_intent_parser."""
from __future__ import annotations

from pydantic import SecretStr

from app.ai.intent import IntentParser
from app.bot.deps import build_intent_parser
from app.config import Settings


def _settings(openai_key: str | None) -> Settings:
    """Settings with telegram_bot_token stub + optional OpenAI key."""
    return Settings(
        telegram_bot_token=SecretStr("test:token"),  # type: ignore[arg-type]
        openai_api_key=SecretStr(openai_key) if openai_key else None,
    )


def test_build_intent_parser_returns_none_when_no_key():
    assert build_intent_parser(_settings(openai_key=None)) is None


def test_build_intent_parser_returns_parser_when_key_present():
    parser = build_intent_parser(_settings(openai_key="sk-fake"))
    assert isinstance(parser, IntentParser)
