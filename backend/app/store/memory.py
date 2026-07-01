"""内存版存储（demo）。进程内保存，重启即失。"""

from __future__ import annotations

from ..models import Segment


class MemoryStore:
    def __init__(self) -> None:
        self._segments: dict[str, list[Segment]] = {}
        self._meta: dict[str, dict] = {}

    def create_session(self, session_id: str, meta: dict | None = None) -> None:
        self._segments.setdefault(session_id, [])
        self._meta[session_id] = meta or {}

    def append(self, session_id: str, segment: Segment) -> None:
        self._segments.setdefault(session_id, []).append(segment)

    def latest_t(self, session_id: str) -> float:
        segs = self._segments.get(session_id)
        return segs[-1].t if segs else 0.0

    def window(self, session_id: str, start_t: float, end_t: float) -> list[Segment]:
        segs = self._segments.get(session_id, [])
        return [s for s in segs if start_t <= s.t <= end_t]
