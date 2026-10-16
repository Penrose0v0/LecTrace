"""跨模块共享的数据结构（全部 pydantic，可直接 model_dump 回给前端）。"""

from __future__ import annotations

from pydantic import BaseModel, Field

LANGS = ("ja", "zh", "en")
SOURCES = ("openai-stt", "google-stt", "google-stt-v2", "replay")


# ---------------- 转录 ----------------
class Segment(BaseModel):
    """一段转录。t 是相对讲义开始的逻辑秒数，是 Catchup 时间窗的唯一时间轴。"""

    seq: int
    text: str
    t: float


class Card(BaseModel):
    """一张 Catchup 摘要卡片（持久化，供日后统计 / 回看）。"""

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
class LectureMeta(BaseModel):
    """一节课的元信息：前端 meta 面板里编辑的内容，全部可选。

    标题 / 描述会作为上下文交给 LLM；将来讲义等上下文也放这里。
    """

    title: str = ""
    description: str = ""
    lecture_language: str = "ja"  # 讲义语言（转录语言）
    user_language: str = "ja"  # 用户语言（摘要 / 对话输出语言）
    window_minutes: float = Field(default=3.0, ge=1, le=30)  # Catch-up 回顾时长
    source: str = "google-stt"  # google-stt（v1）/ google-stt-v2（Chirp 3）/ openai-stt / replay
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


class SessionInfo(LectureMeta):
    """讲义列表 / 详情里返回的会话信息 = 元信息 + 归属 + 统计。"""

    id: str
    user_id: str = ""
    created_at: float = 0.0  # epoch 秒
    updated_at: float = 0.0
    segment_count: int = 0
    latest_t: float = 0.0  # 讲义时长（最后一段的逻辑时间）
    # 录音 take 列表：{path, sample_rate, channels, sample_width, t_offset, started_at, bytes, duration_sec}
    recordings: list[dict] = Field(default_factory=list)


# ---------------- 对话 ----------------
class Conversation(BaseModel):
    """一条对话线程。Catch-up 摘要也存在 messages 里（kind="catchup"）。

    message 形如 {"role": "user"|"assistant", "content": str, "kind"?: "catchup",
                 "covered_from"?, "covered_to"?, "segment_count"?, "index"?, "card_id"?}
    """

    id: str
    session_id: str
    title: str
    created_t: float = 0.0
    messages: list[dict] = Field(default_factory=list)

    def summary(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "created_t": self.created_t,
            "message_count": len(self.messages),
        }


# ---------------- 用户 ----------------
class User(BaseModel):
    id: str
    email: str = ""
    name: str = ""
    picture: str = ""


class UserPrefs(BaseModel):
    ui_language: str = "ja"  # 界面语言（= 默认用户语言）
    lecture_language: str = "ja"
    window_minutes: float = Field(default=3.0, ge=1, le=30)
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
