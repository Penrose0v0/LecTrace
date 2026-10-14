"""LLM 提供方的公共接口 + 共用的 SSE 工具。"""

from __future__ import annotations

import json
from typing import AsyncIterator, Protocol

import httpx

Message = dict  # {"role": "system"|"user"|"assistant", "content": str}


class LLMError(RuntimeError):
    pass


class LLMProvider(Protocol):
    name: str
    model: str

    def stream(
        self, messages: list[Message], *, max_tokens: int, temperature: float
    ) -> AsyncIterator[str]:
        """按 messages 生成，逐块 yield 文本。出错抛 LLMError。"""
        ...


async def sse_json_events(resp: httpx.Response) -> AsyncIterator[dict]:
    """把 SSE 响应的每个 `data: {...}` 行解析成 dict（跳过空行和 [DONE]）。"""
    async for line in resp.aiter_lines():
        if not line.startswith("data:"):
            continue
        data = line[len("data:"):].strip()
        if not data or data == "[DONE]":
            continue
        try:
            yield json.loads(data)
        except json.JSONDecodeError:
            continue


async def raise_for_status(resp: httpx.Response, who: str) -> None:
    if resp.status_code != 200:
        body = (await resp.aread()).decode("utf-8", "replace")
        raise LLMError(f"{who} API 错误 {resp.status_code}: {body[:300]}")
