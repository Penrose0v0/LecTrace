"""LLM 提供方的公共接口 + 共用的 SSE 工具。"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import AsyncIterator, Protocol

import httpx

Message = dict  # {"role": "system"|"user"|"assistant", "content": str}

# 流式请求的超时：connect 短，read 是「两个 chunk 之间」的间隔（开思考时首 token 会晚一些）
STREAM_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)

# 提供方过载 / 限流时在开流前重试几次（SiliconFlow 高峰期常见 503 "System is too busy"）。
# 等待要短：模型真挂了的话，用户应该尽快看到报错，而不是干等
RETRY_STATUSES = (429, 502, 503, 504)
RETRY_DELAYS = (0.5, 1.5)


class LLMError(RuntimeError):
    pass


class LLMProvider(Protocol):
    name: str
    model: str

    def stream(
        self, messages: list[Message], *, max_tokens: int, temperature: float, thinking: bool = False
    ) -> AsyncIterator[str]:
        """按 messages 生成，逐块 yield 文本。出错抛 LLMError。

        thinking=True 允许模型先推理再作答（对话用；Catch-up 要秒回，不开）。
        各提供方自己决定预算，不支持就忽略。
        """
        ...


@asynccontextmanager
async def open_stream(who: str, method: str, url: str, **kwargs) -> AsyncIterator[httpx.Response]:
    """发起流式请求：非 200 抛 LLMError，过载状态码先重试；网络错误也统一成 LLMError。

    用法：async with open_stream("Gemini", "POST", url, json=payload) as resp: ...
    """
    try:
        async with httpx.AsyncClient(timeout=STREAM_TIMEOUT) as client:
            for attempt in range(len(RETRY_DELAYS) + 1):
                async with client.stream(method, url, **kwargs) as resp:
                    if resp.status_code == 200:
                        yield resp
                        return
                    body = (await resp.aread()).decode("utf-8", "replace")
                    if resp.status_code in RETRY_STATUSES and attempt < len(RETRY_DELAYS):
                        await asyncio.sleep(RETRY_DELAYS[attempt])
                        continue
                    raise LLMError(f"{who} API 错误 {resp.status_code}: {body[:300]}")
    except httpx.TimeoutException as exc:
        raise LLMError(f"{who} 响应超时（{type(exc).__name__}）。") from exc
    except httpx.HTTPError as exc:
        raise LLMError(f"{who} 网络错误：{exc}") from exc


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
