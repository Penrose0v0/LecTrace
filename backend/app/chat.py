"""AI 对话：结合课堂转录上下文，与用户多轮对话（Gemini 流式）。

会话保存在内存（demo）。之后可换成 Firestore，把 ConversationStore 换实现即可。
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

from .config import Settings
from .gemini import base_generation_config, stream_generate

_LANG_NAME = {"ja": "日本語", "en": "English", "zh": "中文"}


class Conversation:
    def __init__(self, cid: str, session_id: str, title: str, created_t: float) -> None:
        self.id = cid
        self.session_id = session_id
        self.title = title
        self.created_t = created_t
        self.messages: list[dict] = []  # [{"role": "user"|"assistant", "content": str}]

    def summary(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "created_t": self.created_t,
            "message_count": len(self.messages),
        }


class ConversationStore:
    """内存版会话存储（demo）。"""

    def __init__(self) -> None:
        self._c: dict[str, Conversation] = {}

    def create(self, session_id: str, title: str, created_t: float) -> Conversation:
        cid = uuid.uuid4().hex
        conv = Conversation(cid, session_id, title, created_t)
        self._c[cid] = conv
        return conv

    def get(self, cid: str) -> Conversation | None:
        return self._c.get(cid)

    def list(self, session_id: str) -> list[Conversation]:
        return [c for c in self._c.values() if c.session_id == session_id]


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
