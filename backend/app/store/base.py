"""TranscriptStore 接口。"""

from __future__ import annotations

from typing import Protocol

from ..models import Segment


class TranscriptStore(Protocol):
    def create_session(self, session_id: str, meta: dict | None = None) -> None: ...

    def append(self, session_id: str, segment: Segment) -> None: ...

    def latest_t(self, session_id: str) -> float:
        """已见过的最大逻辑时间 t（讲义“当前时刻”）。空会话返回 0。"""
        ...

    def window(self, session_id: str, start_t: float, end_t: float) -> list[Segment]:
        """取 [start_t, end_t] 内的段落（含端点）。"""
        ...
