"""AI 对话：结合课堂转录上下文，与用户多轮对话（provider 无关，流式）。

会话存储见 conversations.py（内存 / Firestore 可插拔）。
"""

from __future__ import annotations

from typing import AsyncIterator

from .config import Settings
from .llm import stream_chat

_LANG_NAME = {"ja": "日本語", "en": "English", "zh": "中文"}


def _system_prompt(transcript: str, user_lang: str) -> str:
    lang = _LANG_NAME.get(user_lang, user_lang)
    ctx = transcript.strip() or "（まだ文字起こしがありません）"
    return (
        "あなたは講義の理解を助けるアシスタントです。"
        "以下は受講中の講義の文字起こし（直近部分）です。"
        f"この内容を踏まえ、受講者の質問に{lang}で簡潔かつ正確に答えてください。"
        "文字起こしに無い内容は推測だと明示してください。\n\n"
        "--- 講義の文字起こし ---\n"
        f"{ctx}\n"
        "--- ここまで ---"
    )


async def chat_stream(
    messages: list[dict],
    transcript: str,
    user_lang: str,
    settings: Settings,
) -> AsyncIterator[str]:
    """基于对话历史 + 转录上下文，流式产出回复。"""
    neutral = [{"role": "system", "content": _system_prompt(transcript, user_lang)}]
    neutral += [{"role": m["role"], "content": m["content"]} for m in messages]
    async for chunk in stream_chat(neutral, settings, max_tokens=1024, temperature=0.4):
        yield chunk
