"""Production CompleterProtocol — wraps openai.AsyncOpenAI with JSON mode."""
from __future__ import annotations

from openai import AsyncOpenAI

from app.config import get_settings


class OpenAICompleter:
    def __init__(self, client: AsyncOpenAI | None = None, model: str | None = None) -> None:
        if client is None:
            settings = get_settings()
            if settings.openai_api_key is None:
                raise RuntimeError("OPENAI_API_KEY not configured")
            client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())
        self.client = client
        self.model = model or get_settings().openai_model

    async def complete_json(self, system: str, user: str) -> str:
        resp = await self.client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
        )
        return resp.choices[0].message.content or "{}"
