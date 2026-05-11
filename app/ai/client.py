"""Production CompleterProtocol — wraps openai.AsyncOpenAI with JSON mode."""
from __future__ import annotations

from openai import AsyncOpenAI

from app.config import get_settings


class OpenAICompleter:
    def __init__(
        self,
        client: AsyncOpenAI | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> None:
        settings = get_settings()
        if client is None:
            if settings.openai_api_key is None:
                raise RuntimeError("OPENAI_API_KEY not configured")
            client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())
        self.client = client
        self.model = model or settings.openai_model
        self.max_tokens = max_tokens if max_tokens is not None else settings.openai_max_tokens

    async def complete_json(self, system: str, user: str) -> str:
        resp = await self.client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
            max_tokens=self.max_tokens,
        )
        return resp.choices[0].message.content or "{}"
