"""跨模块共享的数据结构。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Segment(BaseModel):
    """一段转录。t 是相对讲义开始的逻辑秒数，是 Catchup 时间窗的唯一时间轴。"""

    seq: int
    text: str
    t: float  # 逻辑时间轴：距讲义开始的秒数


class Card(BaseModel):
    """一张 Catchup 摘要卡片（持久化）。"""

    id: str
    index: int
    covered_from: float
    covered_to: float
    segment_count: int
    model: str
    lecture_language: str
    user_language: str
    summary: str = ""
    created_t: float = 0.0


# ---------------- 讲义（session）----------------
LANGS = ("ja", "zh", "en")
SOURCES = ("openai-stt", "google-stt", "replay")


class LectureMeta(BaseModel):
    """一节课的元信息：前端 meta 面板里编辑的内容。将来讲义等上下文也放这里。"""

    title: str = ""
    description: str = ""
    lecture_language: str = "ja"  # 讲义语言（转录语言）
    user_language: str = "ja"  # 用户语言（摘要 / 对话输出语言）
    window_minutes: float = Field(default=5.0, ge=1, le=30)  # Catch-up 回顾时长
    source: str = "openai-stt"  # openai-stt / google-stt / replay
    file: str = ""  # source=replay 时的归档文件


class LectureUpdate(BaseModel):
    """PATCH 用：只更新给了的字段。"""

    title: str | None = None
    description: str | None = None
    lecture_language: str | None = None
    user_language: str | None = None
    window_minutes: float | None = Field(default=None, ge=1, le=30)
    source: str | None = None
    file: str | None = None


class SessionInfo(BaseModel):
    """讲义列表 / 详情里返回的会话信息（元信息 + 统计）。"""

    id: str
    user_id: str = ""
    title: str = ""
    description: str = ""
    lecture_language: str = "ja"
    user_language: str = "ja"
    window_minutes: float = 5.0
    source: str = "openai-stt"
    file: str = ""
    created_at: float = 0.0  # epoch 秒
    updated_at: float = 0.0
    segment_count: int = 0
    latest_t: float = 0.0  # 讲义时长（最后一段的逻辑时间）


# ---------------- 用户偏好 ----------------
class UserPrefs(BaseModel):
    ui_language: str = "ja"  # 界面语言（= 默认用户语言）
    lecture_language: str = "ja"
    window_minutes: float = Field(default=5.0, ge=1, le=30)
    theme: str = "dark"


# ---------------- 请求体 ----------------
class CatchupRequest(BaseModel):
    session_id: str
    window_minutes: float | None = None  # 不传则用讲义设置
    conversation_id: str | None = None  # 结果追加到哪个对话；没有则新建


class ChatRequest(BaseModel):
    session_id: str
    message: str = ""
    conversation_id: str | None = None
    preset: str | None = None  # "explain" 等快捷指令；设了则 message 可空


class GoogleLoginRequest(BaseModel):
    credential: str
