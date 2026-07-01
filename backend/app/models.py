"""跨模块共享的数据结构。"""

from __future__ import annotations

from pydantic import BaseModel


class Segment(BaseModel):
    """一段转录。t 是相对讲义开始的逻辑秒数，是 Catchup 时间窗的唯一时间轴。"""

    seq: int
    text: str
    t: float  # 逻辑时间轴：距讲义开始的秒数


class CatchupRequest(BaseModel):
    session_id: str
    window_minutes: float = 5.0
    lecture_language: str = "ja"  # 讲义语言（转录语言）
    user_language: str = "ja"  # 用户语言（摘要输出语言）


class ChatRequest(BaseModel):
    session_id: str
    message: str
    conversation_id: str | None = None
    user_language: str = "ja"
