"""LLM 提供方（可插拔）：LLM_PROVIDER=siliconflow（默认）| openai | gemini。

上层只产出「中性消息」列表（见 prompts/），这里按配置选提供方并流式产出文本。
"""

from __future__ import annotations

from ..config import Settings
from .base import LLMError, LLMProvider, LLMUsage, Message


def get_llm(settings: Settings) -> LLMProvider:
    p = settings.llm_provider
    if p == "siliconflow":
        if not settings.siliconflow_api_key:
            raise LLMError("SILICONFLOW_API_KEY 未配置。")
        from .openai import OpenAICompatProvider

        return OpenAICompatProvider(
            settings.siliconflow_api_key, settings.siliconflow_model, settings.siliconflow_base_url,
            name="siliconflow",
            max_tokens_param="max_tokens",
            # Qwen3 系列默认带 thinking，会先推理几千字再作答；Catch-up 要秒回，关掉。
            # 对话（thinking=True）允许想一下，但给个预算别无限推理。
            extra={"enable_thinking": False},
            thinking_extra={"enable_thinking": True, "thinking_budget": settings.chat_thinking_budget},
        )
    if p == "openai":
        if not settings.openai_api_key:
            raise LLMError("OPENAI_API_KEY 未配置。")
        from .openai import OpenAICompatProvider

        return OpenAICompatProvider(settings.openai_api_key, settings.openai_model, settings.openai_base_url)
    if p == "gemini":
        if not settings.gemini_api_key:
            raise LLMError("GEMINI_API_KEY 未配置。")
        from .gemini import GeminiProvider

        return GeminiProvider(
            settings.gemini_api_key, settings.gemini_model, thinking_budget=settings.chat_thinking_budget
        )
    raise LLMError(f"未知 LLM_PROVIDER: {p}")


__all__ = ["LLMError", "LLMProvider", "LLMUsage", "Message", "get_llm"]
