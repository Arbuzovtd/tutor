"""TDD tests for app.bot.deps.build_intent_parser."""
from __future__ import annotations

from pydantic import SecretStr

from app.ai.intent import IntentParser
from app.bot.deps import build_intent_parser
from app.config import Settings


def _settings(
    openai_key: str | None, openai_base_url: str | None = None
) -> Settings:
    """Settings with telegram_bot_token stub + optional OpenAI key / base url."""
    return Settings(
        telegram_bot_token=SecretStr("test:token"),  # type: ignore[arg-type]
        openai_api_key=SecretStr(openai_key) if openai_key else None,
        openai_base_url=openai_base_url,
    )


def test_build_intent_parser_returns_none_when_no_key():
    assert build_intent_parser(_settings(openai_key=None)) is None


def test_build_intent_parser_returns_parser_when_key_present():
    parser = build_intent_parser(_settings(openai_key="sk-fake"))
    assert isinstance(parser, IntentParser)


def test_build_intent_parser_uses_custom_base_url_for_polza():
    """OPENAI_BASE_URL must be forwarded to the AsyncOpenAI client so we can
    point at OpenAI-compatible gateways (e.g. polza.ai).
    """
    parser = build_intent_parser(
        _settings(openai_key="sk-fake", openai_base_url="https://api.polza.ai/v1")
    )
    assert isinstance(parser, IntentParser)
    # AsyncOpenAI normalises base_url to end with "/"
    assert str(parser.completer.client.base_url).rstrip("/") == "https://api.polza.ai/v1"


def test_build_intent_parser_uses_default_base_url_when_unset():
    parser = build_intent_parser(_settings(openai_key="sk-fake"))
    assert isinstance(parser, IntentParser)
    assert "openai.com" in str(parser.completer.client.base_url)


def test_http_base_url_rejected_by_settings():
    import pytest

    with pytest.raises(Exception):
        _settings(openai_key="sk-fake", openai_base_url="http://insecure.example.com/v1")


def test_max_tokens_propagated_to_completer():
    parser = build_intent_parser(_settings(openai_key="sk-fake"))
    assert parser is not None
    # Default settings.openai_max_tokens == 300
    assert parser.completer.max_tokens == 300
