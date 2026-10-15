"""Prompt 加载与填充。文案本身全部在同目录的 {lang}.toml 里，这里不含任何自然语言。

每种用户语言一个 toml，key 完全相同：
  [context]         讲义标题 / 描述怎么拼进上下文
  [catchup]         system / user 模板
  [chat]            system 模板（含 {context} {transcript} {now}）、无转录占位、
                    转录开头被截掉时的说明、Catch-up 历史的前缀
  [presets]         快捷指令（直接作为用户消息）
  [language_names]  语言代码 → 该语言里的叫法（用于「讲义是{lecture_language}的」）

模板用 str.format 占位符；填充值（转录文本等）不会再被解析，含大括号也安全。
找不到用户语言的文件时回落到 en。
"""

from __future__ import annotations

import re
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


def fmt_t(sec: float) -> str:
    """逻辑秒 → 「分:秒」。课程可能超过 1 小时，分钟数不折成小时，省得模型换算。"""
    s = max(0, int(sec))
    return f"{s // 60}:{s % 60:02d}"


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
def format_transcript(segments: list[Segment], max_chars: int, user_lang: str) -> str:
    """整节课的转录 → 带课程时间标记的文本，每分钟一行：

        [39:00] ではここから… 教科書では…
        [40:00] …

    超过 max_chars 时从开头整行丢弃，并在最前面注明省略了多少分钟。
    时间标记让模型能回答「老师大概什么时候讲的」，也让它知道末尾才是「现在」。
    """
    if not segments:
        return ""
    lines: list[tuple[float, str]] = []  # (该分钟起点, 文本)
    cur_min, buf = -1, []
    for s in segments:
        m = int(s.t // 60)
        if m != cur_min:
            if buf:
                lines.append((cur_min * 60.0, " ".join(buf)))
            cur_min, buf = m, []
        if s.text.strip():
            buf.append(s.text.strip())
    if buf:
        lines.append((cur_min * 60.0, " ".join(buf)))

    rendered = [f"[{fmt_t(t)}] {text}" for t, text in lines]
    total = sum(len(r) + 1 for r in rendered)
    dropped = 0
    while dropped < len(rendered) - 1 and total > max_chars:
        total -= len(rendered[dropped]) + 1
        dropped += 1
    out = rendered[dropped:]
    if dropped:
        omitted_minutes = max(1, int(lines[dropped][0] // 60))
        note = load(user_lang)["chat"]["omitted_note"].format(minutes=omitted_minutes)
        out.insert(0, note)
    return "\n".join(out)


def chat_messages(history: list[dict], transcript: str, now_t: float, lecture: LectureMeta) -> list[dict]:
    """system（课程信息 + 整节课转录 + 规则）+ 最近 N 条历史。

    历史里的 user 消息带 [分:秒] 提问时间，Catch-up 摘要带覆盖区间，
    让模型知道「上一次回答时老师讲到哪了」，不会被过时的回答带着走。
    """
    p = load(lecture.user_language)
    system = p["chat"]["system"].format(
        lecture_language=_lang_name(p, lecture.lecture_language),
        context=_context(p, lecture),
        transcript=transcript.strip() or p["chat"]["empty_transcript"],
        now=fmt_t(now_t),
    )
    system = re.sub(r"\n{3,}", "\n\n", system).strip()
    out = [{"role": "system", "content": system}]
    for m in history[-CHAT_HISTORY_LIMIT:]:
        content = m["content"]
        if m.get("kind") == "catchup":
            prefix = p["chat"]["catchup_prefix"].format(
                **{"from": fmt_t(m.get("covered_from", 0.0)), "to": fmt_t(m.get("covered_to", 0.0))}
            )
            content = f"{prefix}\n{content}"
        elif m["role"] == "user" and m.get("t") is not None:
            content = f"[{fmt_t(m['t'])}] {content}"
        out.append({"role": m["role"], "content": content})
    return out


# ---------------- 快捷指令 ----------------
def preset_message(preset: str, user_lang: str) -> str | None:
    return load(user_lang)["presets"].get(preset)
