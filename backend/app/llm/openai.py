"""OpenAI Chat Completions 协议（流式）。OpenAI 本家和兼容服务（SiliconFlow 等）共用。"""

from __future__ import annotations

from typing import AsyncIterator

from .base import LLMUsage, Message, open_stream, sse_json_events


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
        thinking_extra: dict | None = None,
    ) -> None:
        """
        max_tokens_param：OpenAI 新版（gpt-5.x）要求 max_completion_tokens；多数兼容服务只认 max_tokens。
        extra：thinking=False 时附加到请求体的字段（例如 SiliconFlow 的 enable_thinking=False）。
        thinking_extra：thinking=True 时附加的字段（例如 enable_thinking=True + thinking_budget）。
        """
        self.name = name
        self.model = model
        self._api_key = api_key
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._max_tokens_param = max_tokens_param
        self._extra = extra or {}
        self._thinking_extra = thinking_extra or {}

    async def stream(
        self,
        messages: list[Message],
        *,
        max_tokens: int,
        temperature: float,
        thinking: bool = False,
        usage: LLMUsage | None = None,
    ) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            # 让最后一个 chunk 带 usage（OpenAI / SiliconFlow 都支持；不支持的服务会忽略）
            "stream_options": {"include_usage": True},
            "temperature": temperature,
            self._max_tokens_param: max_tokens,
            **(self._thinking_extra if thinking else self._extra),
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        async with open_stream(self.name, "POST", self._url, headers=headers, json=payload) as resp:
            async for obj in sse_json_events(resp):
                if usage is not None and (u := obj.get("usage")):
                    usage.set(u.get("prompt_tokens"), u.get("completion_tokens"))
                choices = obj.get("choices") or []
                if not choices:
                    continue
                # 思考内容走 delta.reasoning_content，这里只要正文
                delta = choices[0].get("delta", {}).get("content")
                if delta:
                    yield delta
