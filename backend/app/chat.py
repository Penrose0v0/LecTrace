"""AI 对话：结合课堂转录上下文，与用户多轮对话（Gemini 流式）。

会话存储见 conversations.py（内存 / Firestore 可插拔）。
"""

from __future__ import annotations

from typing import AsyncIterator

from .config import Settings
from .gemini import base_generation_config, stream_generate

_LANG_NAME = {"ja": "日本語", "en": "English", "zh": "中文"}


def _system_instruction(transcript: str, user_lang: str) -> dict:
    lang = _LANG_NAME.get(user_lang, user_lang)
    ctx = transcript.strip() or "（まだ文字起こしがありません）"
    text = (
        "あなたは講義の理解を助けるアシスタントです。"
        "以下は受講中の講義の文字起こし（直近部分）です。"
        f"この内容を踏まえ、受講者の質問に{lang}で簡潔かつ正確に答えてください。"
        "文字起こしに無い内容は推測だと明示してください。\n\n"
        "--- 講義の文字起こし ---\n"
        f"{ctx}\n"
        "--- ここまで ---"
    )
    return {"parts": [{"text": text}]}


async def chat_stream(
    messages: list[dict],
    transcript: str,
    user_lang: str,
    settings: Settings,
) -> AsyncIterator[str]:
    """基于对话历史 + 转录上下文，流式产出回复。"""
    contents = [
        {
            "role": "user" if m["role"] == "user" else "model",
            "parts": [{"text": m["content"]}],
        }
        for m in messages
    ]
    payload = {
        "systemInstruction": _system_instruction(transcript, user_lang),
        "contents": contents,
        "generationConfig": base_generation_config(max_tokens=1024, temperature=0.4),
    }
    async for chunk in stream_generate(payload, settings):
        yield chunk
