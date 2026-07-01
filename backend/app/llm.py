"""LLM 提供方抽象（可插拔）：OpenAI / Gemini。

上层（summarize / chat）只产出「中性消息」列表：
    [{"role": "system"|"user"|"assistant", "content": str}, ...]
本模块按 settings.llm_provider 转成各家 wire 格式并流式产出文本。
"""

from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from .config import Settings
from .gemini import GeminiError, base_generation_config
from .gemini import stream_generate as _gemini_stream_generate


class LLMError(RuntimeError):
    pass


async def stream_chat(
    messages: list[dict],
    settings: Settings,
    *,
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> AsyncIterator[str]:
    if not settings.llm_configured:
        raise LLMError("LLM 未配置 API key。")
    if settings.llm_provider == "openai":
        gen = _openai_stream(messages, settings, max_tokens, temperature)
    elif settings.llm_provider == "gemini":
        gen = _gemini_stream(messages, settings, max_tokens, temperature)
    else:
        raise LLMError(f"未知 LLM_PROVIDER: {settings.llm_provider}")
    async for chunk in gen:
        yield chunk


# ---------------- OpenAI ----------------
async def _openai_stream(
    messages: list[dict], settings: Settings, max_tokens: int, temperature: float
) -> AsyncIterator[str]:
    url = settings.openai_base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": settings.openai_model,
        "messages": messages,
        "stream": True,
        "temperature": temperature,
        # 新版规范参数（gpt-5.x 要求；gpt-4o 系列也兼容）
        "max_completion_tokens": max_tokens,
    }
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as resp:
            if resp.status_code != 200:
                body = (await resp.aread()).decode("utf-8", "replace")
                raise LLMError(f"OpenAI API 错误 {resp.status_code}: {body[:300]}")
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
                choices = obj.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta", {}).get("content")
                if delta:
                    yield delta


# ---------------- Gemini ----------------
def _to_gemini_payload(messages: list[dict], max_tokens: int, temperature: float) -> dict:
    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    contents = [
        {"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]}
        for m in messages
        if m["role"] in ("user", "assistant")
    ]
    payload: dict = {
        "contents": contents,
        "generationConfig": base_generation_config(max_tokens=max_tokens, temperature=temperature),
    }
    if system_parts:
        payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
    return payload


async def _gemini_stream(
    messages: list[dict], settings: Settings, max_tokens: int, temperature: float
) -> AsyncIterator[str]:
    payload = _to_gemini_payload(messages, max_tokens, temperature)
    try:
        async for chunk in _gemini_stream_generate(payload, settings):
            yield chunk
    except GeminiError as exc:
        raise LLMError(str(exc)) from exc
