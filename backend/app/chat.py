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


# 快捷指令：对话里显示的短句（也直接作为用户消息发给 LLM）
PRESETS: dict[str, dict[str, str]] = {
    "explain": {
        "ja": "先生がたった今（直近1〜2分）話している用語・概念を、初めて聞く人向けに簡潔に説明して。",
        "zh": "解释一下老师刚才（最近一两分钟）提到的术语或概念，面向第一次听到的人，简洁一点。",
        "en": "Explain the term or concept the lecturer is talking about right now (last 1–2 minutes), briefly, for someone hearing it for the first time.",
    },
}

# 送给 LLM 的历史条数上限（含 Catch-up 摘要）
HISTORY_LIMIT = 20


def preset_message(preset: str, user_lang: str) -> str | None:
    p = PRESETS.get(preset)
    if not p:
        return None
    return p.get(user_lang) or p["en"]


async def chat_stream(
    messages: list[dict],
    transcript: str,
    user_lang: str,
    settings: Settings,
) -> AsyncIterator[str]:
    """基于对话历史 + 转录上下文，流式产出回复。

    历史里 kind=catchup 的助手消息（Catch-up 摘要）也一并带上，让对话能引用它。
    """
    neutral = [{"role": "system", "content": _system_prompt(transcript, user_lang)}]
    for m in messages[-HISTORY_LIMIT:]:
        content = m["content"]
        if m.get("kind") == "catchup":
            content = f"[Catch-up summary]\n{content}"
        neutral.append({"role": m["role"], "content": content})
    async for chunk in stream_chat(neutral, settings, max_tokens=1024, temperature=0.4):
        yield chunk
