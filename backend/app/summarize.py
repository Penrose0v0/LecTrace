"""Catchup 摘要：把最近 X 分钟的转录交给 Gemini 流式总结。"""

from __future__ import annotations

from typing import AsyncIterator

from .config import Settings
from .gemini import base_generation_config, stream_generate
from .models import Segment

_LANG_NAME = {"ja": "日本語", "en": "English", "zh": "中文"}


def _lang(code: str) -> str:
    return _LANG_NAME.get(code, code)


def _build_prompt(
    segments: list[Segment],
    window_minutes: float,
    lecture_lang: str,
    user_lang: str,
) -> str:
    transcript = "\n".join(s.text for s in segments)
    lecture_name = _lang(lecture_lang)
    user_name = _lang(user_lang)
    return (
        "あなたは講義の「聞き逃しキャッチアップ」を助けるアシスタントです。\n"
        f"以下は{lecture_name}で行われた講義の、直近およそ {window_minutes:.0f} 分間の"
        "文字起こしです。受講者が少し集中を切らして聞き逃した内容を、すばやく"
        f"追いつけるようにまとめてください。\n\n"
        "要件:\n"
        "- 冒頭に1文で「今なにを話しているか」を要約\n"
        "- そのあと重要ポイントを3〜6個の箇条書きで\n"
        "- 専門用語・固有名詞・数値はそのまま残す\n"
        "- 前置きや自己言及は書かない\n"
        f"- 出力は必ず{user_name}で書く\n\n"
        "--- 文字起こし ---\n"
        f"{transcript}\n"
        "--- ここまで ---"
    )


async def summarize_stream(
    segments: list[Segment],
    window_minutes: float,
    lecture_lang: str,
    user_lang: str,
    settings: Settings,
) -> AsyncIterator[str]:
    """逐块产出摘要文本（token 片段）。"""
    prompt = _build_prompt(segments, window_minutes, lecture_lang, user_lang)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": base_generation_config(max_tokens=1024, temperature=0.3),
    }
    async for chunk in stream_generate(payload, settings):
        yield chunk
