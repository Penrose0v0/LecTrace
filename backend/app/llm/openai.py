"""OpenAI Chat Completions 协议（流式）。OpenAI 本家和兼容服务（SiliconFlow 等）共用。"""

from __future__ import annotations

from typing import AsyncIterator

import httpx

from .base import Message, raise_for_status, sse_json_events


class OpenAICompatProvider:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        *,
        name: str = "openai",
        max_tokens_param: str = "max_completion_tokens",
        extra: dict | None = None,
    ) -> None:
        """
        max_tokens_param：OpenAI 新版（gpt-5.x）要求 max_completion_tokens；多数兼容服务只认 max_tokens。
        extra：固定附加到请求体的字段（例如 SiliconFlow 的 enable_thinking=False）。
        """
        self.name = name
        self.model = model
        self._api_key = api_key
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._max_tokens_param = max_tokens_param
        self._extra = extra or {}

    async def stream(
        self, messages: list[Message], *, max_tokens: int, temperature: float
    ) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
            self._max_tokens_param: max_tokens,
            **self._extra,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", self._url, headers=headers, json=payload) as resp:
                await raise_for_status(resp, self.name)
                async for obj in sse_json_events(resp):
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {}).get("content")
                    if delta:
                        yield delta
