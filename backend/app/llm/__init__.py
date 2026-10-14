"""LLM 提供方（可插拔）：LLM_PROVIDER=openai | gemini。

上层只产出「中性消息」列表（见 prompts.py），这里按配置选提供方并流式产出文本。
"""

from __future__ import annotations

from ..config import Settings
from .base import LLMError, LLMProvider, Message


def get_llm(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "openai":
        if not settings.openai_api_key:
            raise LLMError("OPENAI_API_KEY 未配置。")
        from .openai import OpenAIProvider

        return OpenAIProvider(settings.openai_api_key, settings.openai_model, settings.openai_base_url)
    if settings.llm_provider == "gemini":
        if not settings.gemini_api_key:
            raise LLMError("GEMINI_API_KEY 未配置。")
        from .gemini import GeminiProvider

        return GeminiProvider(settings.gemini_api_key, settings.gemini_model)
    raise LLMError(f"未知 LLM_PROVIDER: {settings.llm_provider}")


__all__ = ["LLMError", "LLMProvider", "Message", "get_llm"]
