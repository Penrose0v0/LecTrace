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
    # 只要一两句话；上限设小，既快又防止模型啰嗦。永远不开思考，要秒回
    async for chunk in llm.stream(messages, max_tokens=160, temperature=0.3):
        yield chunk


async def chat_stream(
    history: list[dict],
    transcript: str,
    now_t: float,
    lecture: LectureMeta,
    settings: Settings,
) -> AsyncIterator[str]:
    """基于对话历史 + 整节课转录上下文，流式产出回复。"""
    llm = get_llm(settings)
    messages = prompts.chat_messages(history, transcript, now_t, lecture)
    async for chunk in llm.stream(
        messages, max_tokens=1500, temperature=0.4, thinking=settings.chat_thinking
    ):
        yield chunk
