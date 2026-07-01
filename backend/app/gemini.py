"""Gemini 流式调用的共享封装（Catchup 摘要与 AI 对话都用它）。

用 httpx 直接调 streamGenerateContent（SSE），逐块产出文本，无额外 SDK 依赖。
之后若改走 Vertex AI，只需替换此文件。
"""

from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from .config import Settings

_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:streamGenerateContent"
)


class GeminiError(RuntimeError):
    pass


async def stream_generate(payload: dict, settings: Settings) -> AsyncIterator[str]:
    """把 payload 发给 Gemini，逐块 yield 文本片段。"""
    if not settings.gemini_configured:
        raise GeminiError("GEMINI_API_KEY 未配置，无法调用 Gemini。")

    url = _ENDPOINT.format(model=settings.gemini_model)
    emitted = False
    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream(
            "POST",
            url,
            params={"key": settings.gemini_api_key, "alt": "sse"},
            json=payload,
        ) as resp:
            if resp.status_code != 200:
                body = (await resp.aread()).decode("utf-8", "replace")
                raise GeminiError(f"Gemini API 错误 {resp.status_code}: {body[:300]}")

            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                for cand in obj.get("candidates", []):
                    for part in cand.get("content", {}).get("parts", []):
                        text = part.get("text")
                        if text:
                            emitted = True
                            yield text
                    reason = cand.get("finishReason")
                    if reason and reason not in ("STOP", "MAX_TOKENS"):
                        raise GeminiError(f"Gemini 生成中止 (finishReason={reason})。")

    if not emitted:
        raise GeminiError("Gemini 未返回文本内容（可能被 token 上限截断）。")


def base_generation_config(max_tokens: int = 1024, temperature: float = 0.3) -> dict:
    """默认关掉 thinking：低延迟且避免思考 token 吃满预算导致截断。"""
    return {
        "temperature": temperature,
        "maxOutputTokens": max_tokens,
        "thinkingConfig": {"thinkingBudget": 0},
    }
