"""Store 接口：讲义会话 / 转录段落 / Catch-up 卡片 / 对话线程 / 用户偏好。

做成 async 接口，便于 Firestore（AsyncClient）无阻塞接入；内存实现里只是形式上 async。
"""

from __future__ import annotations

from typing import Protocol

from ..models import Card, Conversation, Segment, SessionInfo, User, UserPrefs


class Store(Protocol):
    # ---- 会话（讲义）----
    async def create_session(self, session_id: str, meta: dict) -> None: ...

    async def get_session(self, session_id: str) -> SessionInfo | None:
        """会话元信息 + 统计；不存在返回 None。"""
        ...

    async def update_session(self, session_id: str, patch: dict) -> None:
        """只改给定字段（并刷新 updated_at）。"""
        ...

    async def list_sessions(self, user_id: str) -> list[SessionInfo]:
        """某用户的全部讲义，按 created_at 降序。"""
        ...

    async def add_recording(self, session_id: str, info: dict) -> None:
        """追加一个录音 take 的元信息（见 recording.py）。"""
        ...

    async def delete_session(self, session_id: str) -> None:
        """删掉会话及其段落、卡片、对话线程。录音文件由调用方另删（见 recording.delete_recordings）。"""
        ...

    # ---- 转录段落 ----
    async def append(self, session_id: str, segment: Segment) -> None: ...

    async def all_segments(self, session_id: str) -> list[Segment]:
        """会话全部段落（回看 / resume 续接时取末尾 seq/t）。"""
        ...

    async def latest_t(self, session_id: str) -> float:
        """已见过的最大逻辑时间 t（讲义“当前时刻”）。空会话返回 0。"""
        ...

    async def window(self, session_id: str, start_t: float, end_t: float) -> list[Segment]:
        """取 [start_t, end_t] 内的段落（含端点）。"""
        ...

    # ---- Catch-up 卡片 ----
    async def add_card(self, session_id: str, card: Card) -> None: ...

    async def list_cards(self, session_id: str) -> list[Card]:
        """按 index 升序。"""
        ...

    async def card_count(self, session_id: str) -> int: ...

    # ---- 对话线程 ----
    async def create_conversation(self, session_id: str, title: str, created_t: float) -> Conversation: ...

    async def get_conversation(self, cid: str) -> Conversation | None: ...

    async def list_conversations(self, session_id: str) -> list[Conversation]:
        """按 created_t 降序。"""
        ...

    async def save_conversation(self, conv: Conversation) -> None: ...

    # ---- 用户偏好 ----
    async def get_prefs(self, user_id: str) -> UserPrefs | None: ...

    async def save_prefs(self, user_id: str, prefs: UserPrefs) -> None: ...

    # ---- 用户资料 / 用量（见 usage.py）----
    async def touch_user(self, user: User, *, login: bool) -> None:
        """写入 / 刷新用户资料（email、name、picture），更新 last_seen_at；login=True 还加 login_count、
        记 first_login_at / last_login_at。"""
        ...

    async def add_usage(self, user_id: str, day: str, fields: dict) -> None:
        """把 fields 里的数值累加到用户累计 usage 和当日 usage（day = YYYY-MM-DD）。"""
        ...

    async def day_usage(self, user_id: str, day: str) -> dict:
        """某用户某天的 usage；没有返回 {}。"""
        ...

    async def add_event(self, user_id: str, event: dict) -> None:
        """追加一条用量明细（LLM 调用 / 转录连接）。"""
        ...

    async def list_users(self) -> list[dict]:
        """全部用户资料 + 累计 usage（管理后台用），按 last_seen_at 降序。"""
        ...

    async def list_user_days(self, user_id: str, limit: int) -> list[dict]:
        """某用户最近若干天的 usage（含 day 字段），按日期降序。"""
        ...

    async def list_user_events(self, user_id: str, limit: int) -> list[dict]:
        """某用户最近若干条用量明细，按 ts 降序。"""
        ...
