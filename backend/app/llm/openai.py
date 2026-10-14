"""OpenAI Chat Completions（流式）。"""

from __future__ import annotations

from typing import AsyncIterator

import httpx

from .base import Message, raise_for_status, sse_json_events


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        self._api_key = api_key
        self.model = model
        self._url = base_url.rstrip("/") + "/chat/completions"

    async def stream(
        self, messages: list[Message], *, max_tokens: int, temperature: float
    ) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
            # 新版规范参数（gpt-5.x 要求；gpt-4o 系列也兼容）
            "max_completion_tokens": max_tokens,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", self._url, headers=headers, json=payload) as resp:
                await raise_for_status(resp, "OpenAI")
                async for obj in sse_json_events(resp):
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {}).get("content")
                    if delta:
                        yield delta
