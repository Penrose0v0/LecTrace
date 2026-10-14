"""TranscriptStore 接口。

存储被做成 async 接口，便于 Firestore（AsyncClient）等真实后端无阻塞接入。
内存实现里这些方法只是形式上 async。
"""

from __future__ import annotations

from typing import Protocol

from ..models import Card, Segment, SessionInfo, UserPrefs


class TranscriptStore(Protocol):
    # ---- 会话（讲义）----
    async def create_session(self, session_id: str, meta: dict | None = None) -> None: ...

    async def get_session(self, session_id: str) -> SessionInfo | None:
        """会话元信息 + 统计；不存在返回 None。"""
        ...

    async def update_session(self, session_id: str, patch: dict) -> None:
        """只改给定字段（并刷新 updated_at）。"""
        ...

    async def list_sessions(self, user_id: str) -> list[SessionInfo]:
        """某用户的全部讲义，按 created_at 降序。"""
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

    # ---- Catchup 卡片 ----
    async def add_card(self, session_id: str, card: Card) -> None: ...

    async def list_cards(self, session_id: str) -> list[Card]:
        """按 index 升序返回该会话的所有卡片。"""
        ...

    async def card_count(self, session_id: str) -> int: ...

    # ---- 用户偏好 ----
    async def get_prefs(self, user_id: str) -> UserPrefs | None: ...

    async def save_prefs(self, user_id: str, prefs: UserPrefs) -> None: ...
