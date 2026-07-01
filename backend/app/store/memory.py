"""内存版存储（demo 默认）。进程内保存，重启即失。"""

from __future__ import annotations

from ..models import Card, Segment


class MemoryStore:
    def __init__(self) -> None:
        self._segments: dict[str, list[Segment]] = {}
        self._meta: dict[str, dict] = {}
        self._cards: dict[str, list[Card]] = {}

    async def create_session(self, session_id: str, meta: dict | None = None) -> None:
        self._segments.setdefault(session_id, [])
        self._cards.setdefault(session_id, [])
        self._meta[session_id] = meta or {}

    async def append(self, session_id: str, segment: Segment) -> None:
        self._segments.setdefault(session_id, []).append(segment)

    async def latest_t(self, session_id: str) -> float:
        segs = self._segments.get(session_id)
        return segs[-1].t if segs else 0.0

    async def window(self, session_id: str, start_t: float, end_t: float) -> list[Segment]:
        segs = self._segments.get(session_id, [])
        return [s for s in segs if start_t <= s.t <= end_t]

    async def add_card(self, session_id: str, card: Card) -> None:
        self._cards.setdefault(session_id, []).append(card)

    async def list_cards(self, session_id: str) -> list[Card]:
        return sorted(self._cards.get(session_id, []), key=lambda c: c.index)

    async def card_count(self, session_id: str) -> int:
        return len(self._cards.get(session_id, []))
