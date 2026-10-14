"""AI 服务层：Catch-up 摘要 / 对话。只做「拼 prompt → 调 LLM → 流式产出」。"""

from __future__ import annotations

from typing import AsyncIterator

from . import prompts
from .config import Settings
from .llm import get_llm
from .models import LectureMeta, Segment


async def summarize_stream(
    segments: list[Segment],
    window_minutes: float,
    lecture: LectureMeta,
    settings: Settings,
) -> AsyncIterator[str]:
    """最近 X 分钟的转录 → 摘要（逐块产出）。"""
    llm = get_llm(settings)
    messages = prompts.catchup_messages(segments, window_minutes, lecture)
    async for chunk in llm.stream(messages, max_tokens=1024, temperature=0.3):
        yield chunk


async def chat_stream(
    history: list[dict],
    transcript: str,
    lecture: LectureMeta,
    settings: Settings,
) -> AsyncIterator[str]:
    """基于对话历史 + 最近转录上下文，流式产出回复。"""
    llm = get_llm(settings)
    messages = prompts.chat_messages(history, transcript, lecture)
    async for chunk in llm.stream(messages, max_tokens=1024, temperature=0.4):
        yield chunk
