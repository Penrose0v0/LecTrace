"""所有发给 LLM 的 prompt 都在这里。改措辞只动这一个文件。

每个函数返回「中性消息」列表 [{"role": system|user|assistant, "content": str}, ...]，
由 llm 包转成各家 wire 格式。
"""

from __future__ import annotations

from .models import LectureMeta, Segment

LANG_NAME = {"ja": "日本語", "en": "English", "zh": "中文"}


def lang_name(code: str) -> str:
    return LANG_NAME.get(code, code)


# ---------------- 课堂上下文（标题 / 描述）----------------
def lecture_context(lecture: LectureMeta) -> str:
    """把课堂元信息拼成一小段上下文；没填就返回空串。"""
    lines = []
    if lecture.title.strip():
        lines.append(f"講義名: {lecture.title.strip()}")
    if lecture.description.strip():
        lines.append(f"講義の説明: {lecture.description.strip()}")
    return "\n".join(lines)


def _with_context(lecture: LectureMeta, body: str) -> str:
    ctx = lecture_context(lecture)
    return f"{ctx}\n\n{body}" if ctx else body


# ---------------- Catch-up 摘要 ----------------
def catchup_messages(
    segments: list[Segment],
    window_minutes: float,
    lecture: LectureMeta,
) -> list[dict]:
    """最近 X 分钟的转录 → 「你刚才错过了什么」。"""
    transcript = "\n".join(s.text for s in segments)
    lecture_lang = lang_name(lecture.lecture_language)
    user_lang = lang_name(lecture.user_language)

    # 显式的 system 指令强制输出语言（gpt-4o-mini 对嵌在正文里的语言要求不够听话）
    system = (
        "You help students catch up on lectures. "
        f"Always write your entire answer in {user_lang}, "
        "regardless of the transcript's language."
    )
    user = (
        "あなたは講義の「聞き逃しキャッチアップ」を助けるアシスタントです。\n"
        f"以下は{lecture_lang}で行われた講義の、直近およそ {window_minutes:.0f} 分間の"
        "文字起こしです。受講者が少し集中を切らして聞き逃した内容を、すばやく"
        "追いつけるようにまとめてください。\n\n"
        "要件:\n"
        "- 冒頭に1文で「今なにを話しているか」を要約\n"
        "- そのあと重要ポイントを3〜6個の箇条書きで\n"
        "- 専門用語・固有名詞・数値はそのまま残す\n"
        "- 前置きや自己言及は書かない\n"
        f"- 出力は必ず{user_lang}で書く\n\n"
        "--- 文字起こし ---\n"
        f"{transcript}\n"
        "--- ここまで ---"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": _with_context(lecture, user)},
    ]


# ---------------- 对话 ----------------
# 送给 LLM 的历史条数上限（含 Catch-up 摘要）
CHAT_HISTORY_LIMIT = 20


def chat_messages(
    history: list[dict],
    transcript: str,
    lecture: LectureMeta,
) -> list[dict]:
    """对话：system 带课堂上下文 + 最近转录，然后是多轮历史。"""
    user_lang = lang_name(lecture.user_language)
    ctx = transcript.strip() or "（まだ文字起こしがありません）"
    system = (
        "あなたは講義の理解を助けるアシスタントです。"
        "以下は受講中の講義の文字起こし（直近部分）です。"
        f"この内容を踏まえ、受講者の質問に{user_lang}で簡潔かつ正確に答えてください。"
        "文字起こしに無い内容は推測だと明示してください。\n\n"
        "--- 講義の文字起こし ---\n"
        f"{ctx}\n"
        "--- ここまで ---"
    )
    out = [{"role": "system", "content": _with_context(lecture, system)}]
    for m in history[-CHAT_HISTORY_LIMIT:]:
        content = m["content"]
        if m.get("kind") == "catchup":  # 让对话能引用之前的 Catch-up 摘要
            content = f"[Catch-up summary]\n{content}"
        out.append({"role": m["role"], "content": content})
    return out


# ---------------- 快捷指令（对话里显示的短句，也直接作为用户消息发给 LLM）----------------
PRESETS: dict[str, dict[str, str]] = {
    "explain": {
        "ja": "先生がたった今（直近1〜2分）話している用語・概念を、初めて聞く人向けに簡潔に説明して。",
        "zh": "解释一下老师刚才（最近一两分钟）提到的术语或概念，面向第一次听到的人，简洁一点。",
        "en": "Explain the term or concept the lecturer is talking about right now (last 1–2 minutes), briefly, for someone hearing it for the first time.",
    },
}


def preset_message(preset: str, user_lang: str) -> str | None:
    p = PRESETS.get(preset)
    if not p:
        return None
    return p.get(user_lang) or p["en"]
