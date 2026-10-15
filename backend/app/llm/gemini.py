"""Gemini generateContent（流式 SSE）。无 SDK 依赖，改走 Vertex AI 时只换这个文件。"""

from __future__ import annotations

from typing import AsyncIterator

from .base import LLMError, LLMUsage, Message, open_stream, sse_json_events

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent"


def to_gemini_payload(
    messages: list[Message], max_tokens: int, temperature: float, thinking_budget: int
) -> dict:
    """中性消息 → Gemini 格式：system 合并进 systemInstruction，assistant → model。

    thinking_budget=0 关掉思考（Catch-up）；>0 时 maxOutputTokens 要把它加上，因为 Gemini 把思考 token 也算在内。
    """
    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    contents = [
        {"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]}
        for m in messages
        if m["role"] in ("user", "assistant")
    ]
    budget = max(0, thinking_budget)
    payload: dict = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            # Gemini 的 maxOutputTokens 把思考 token 也算在内，开思考时要把预算加上，否则正文被截断
            "maxOutputTokens": max_tokens + budget,
            # Catch-up 关掉 thinking：低延迟，且避免思考 token 吃满预算导致截断
            "thinkingConfig": {"thinkingBudget": budget},
        },
    }
    if system_parts:
        payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
    return payload


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str, *, thinking_budget: int = 1024) -> None:
        self._api_key = api_key
        self.model = model
        self._thinking_budget = thinking_budget

    async def stream(
        self,
        messages: list[Message],
        *,
        max_tokens: int,
        temperature: float,
        thinking: bool = False,
        usage: LLMUsage | None = None,
    ) -> AsyncIterator[str]:
        url = _ENDPOINT.format(model=self.model)
        payload = to_gemini_payload(messages, max_tokens, temperature, self._thinking_budget if thinking else 0)
        emitted = False
        async with open_stream(
            "Gemini", "POST", url, params={"key": self._api_key, "alt": "sse"}, json=payload
        ) as resp:
            async for obj in sse_json_events(resp):
                # 每个 chunk 都带累计 usageMetadata，取最后一次即总量；思考 token 算进输出
                if usage is not None and (um := obj.get("usageMetadata")):
                    usage.set(
                        um.get("promptTokenCount"),
                        (um.get("candidatesTokenCount") or 0) + (um.get("thoughtsTokenCount") or 0),
                    )
                for cand in obj.get("candidates", []):
                    for part in cand.get("content", {}).get("parts", []):
                        if part.get("thought"):
                            continue
                        text = part.get("text")
                        if text:
                            emitted = True
                            yield text
                    reason = cand.get("finishReason")
                    if reason and reason not in ("STOP", "MAX_TOKENS"):
                        raise LLMError(f"Gemini 生成中止 (finishReason={reason})。")
        if not emitted:
            raise LLMError("Gemini 未返回文本内容（可能被 token 上限截断）。")
