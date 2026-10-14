"""Gemini generateContent（流式 SSE）。无 SDK 依赖，改走 Vertex AI 时只换这个文件。"""

from __future__ import annotations

from typing import AsyncIterator

import httpx

from .base import LLMError, Message, raise_for_status, sse_json_events

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent"


def to_gemini_payload(messages: list[Message], max_tokens: int, temperature: float) -> dict:
    """中性消息 → Gemini 格式：system 合并进 systemInstruction，assistant → model。"""
    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    contents = [
        {"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]}
        for m in messages
        if m["role"] in ("user", "assistant")
    ]
    payload: dict = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            # 默认关掉 thinking：低延迟，且避免思考 token 吃满预算导致截断
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    if system_parts:
        payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
    return payload


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self.model = model

    async def stream(
        self, messages: list[Message], *, max_tokens: int, temperature: float
    ) -> AsyncIterator[str]:
        url = _ENDPOINT.format(model=self.model)
        payload = to_gemini_payload(messages, max_tokens, temperature)
        emitted = False
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST", url, params={"key": self._api_key, "alt": "sse"}, json=payload
            ) as resp:
                await raise_for_status(resp, "Gemini")
                async for obj in sse_json_events(resp):
                    for cand in obj.get("candidates", []):
                        for part in cand.get("content", {}).get("parts", []):
                            text = part.get("text")
                            if text:
                                emitted = True
                                yield text
                        reason = cand.get("finishReason")
                        if reason and reason not in ("STOP", "MAX_TOKENS"):
                            raise LLMError(f"Gemini 生成中止 (finishReason={reason})。")
        if not emitted:
            raise LLMError("Gemini 未返回文本内容（可能被 token 上限截断）。")
