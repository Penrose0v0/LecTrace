"""Prompt 加载与填充。文案本身全部在同目录的 {lang}.toml 里，这里不含任何自然语言。

每种用户语言一个 toml，key 完全相同：
  [context]         讲义标题 / 描述怎么拼进上下文
  [catchup]         system / user 模板
  [chat]            system 模板、无转录时的占位、Catch-up 历史的前缀
  [presets]         快捷指令（直接作为用户消息）
  [language_names]  语言代码 → 该语言里的叫法（用于「讲义是{lecture_language}的」）

模板用 str.format 占位符；填充值（转录文本等）不会再被解析，含大括号也安全。
找不到用户语言的文件时回落到 en。
"""

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path

from ..models import LectureMeta, Segment

_DIR = Path(__file__).resolve().parent
_FALLBACK = "en"

# 送给 LLM 的对话历史条数上限（含 Catch-up 摘要）
CHAT_HISTORY_LIMIT = 20


@lru_cache
def load(lang: str) -> dict:
    path = _DIR / f"{lang}.toml"
    if not path.exists():
        path = _DIR / f"{_FALLBACK}.toml"
    with path.open("rb") as f:
        return tomllib.load(f)


def _lang_name(p: dict, code: str) -> str:
    return p["language_names"].get(code, code)


def _context(p: dict, lecture: LectureMeta) -> str:
    """讲义标题 / 描述 → 一小段上下文；没填就是空串。"""
    lines = []
    if lecture.title.strip():
        lines.append(p["context"]["title"].format(title=lecture.title.strip()))
    if lecture.description.strip():
        lines.append(p["context"]["description"].format(description=lecture.description.strip()))
    return "\n".join(lines)


def _system(p: dict, text: str, lecture: LectureMeta) -> dict:
    ctx = _context(p, lecture)
    return {"role": "system", "content": f"{text.strip()}\n\n{ctx}" if ctx else text.strip()}


# ---------------- Catch-up ----------------
def catchup_messages(segments: list[Segment], window_minutes: float, lecture: LectureMeta) -> list[dict]:
    p = load(lecture.user_language)
    user = p["catchup"]["user"].format(
        window_minutes=f"{window_minutes:.0f}",
        lecture_language=_lang_name(p, lecture.lecture_language),
        transcript="\n".join(s.text for s in segments),
    )
    return [_system(p, p["catchup"]["system"], lecture), {"role": "user", "content": user.strip()}]


# ---------------- 对话 ----------------
def chat_messages(history: list[dict], transcript: str, lecture: LectureMeta) -> list[dict]:
    p = load(lecture.user_language)
    system = p["chat"]["system"].format(
        lecture_language=_lang_name(p, lecture.lecture_language),
        transcript=transcript.strip() or p["chat"]["empty_transcript"],
    )
    out = [_system(p, system, lecture)]
    for m in history[-CHAT_HISTORY_LIMIT:]:
        content = m["content"]
        if m.get("kind") == "catchup":  # 让对话能引用之前的 Catch-up 摘要
            content = f"{p['chat']['catchup_prefix']}\n{content}"
        out.append({"role": m["role"], "content": content})
    return out


# ---------------- 快捷指令 ----------------
def preset_message(preset: str, user_lang: str) -> str | None:
    return load(user_lang)["presets"].get(preset)
