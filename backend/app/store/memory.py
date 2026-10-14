"""内存版存储（demo 默认）。进程内保存，重启即失。"""

from __future__ import annotations

import time

from ..models import Card, Segment, SessionInfo, UserPrefs


class MemoryStore:
    def __init__(self) -> None:
        self._segments: dict[str, list[Segment]] = {}
        self._meta: dict[str, dict] = {}
        self._cards: dict[str, list[Card]] = {}
        self._prefs: dict[str, UserPrefs] = {}

    # ---- 会话 ----
    async def create_session(self, session_id: str, meta: dict | None = None) -> None:
        now = time.time()
        self._segments.setdefault(session_id, [])
        self._cards.setdefault(session_id, [])
        self._meta[session_id] = {"created_at": now, "updated_at": now, **(meta or {})}

    async def get_session(self, session_id: str) -> SessionInfo | None:
        meta = self._meta.get(session_id)
        if meta is None:
            return None
        return self._info(session_id, meta)

    async def update_session(self, session_id: str, patch: dict) -> None:
        meta = self._meta.get(session_id)
        if meta is None:
            return
        meta.update(patch)
        meta["updated_at"] = time.time()

    async def list_sessions(self, user_id: str) -> list[SessionInfo]:
        out = [self._info(sid, m) for sid, m in self._meta.items() if m.get("user_id") == user_id]
        out.sort(key=lambda s: s.created_at, reverse=True)
        return out

    def _info(self, session_id: str, meta: dict) -> SessionInfo:
        segs = self._segments.get(session_id, [])
        known = {k: v for k, v in meta.items() if k in SessionInfo.model_fields}
        return SessionInfo(
            id=session_id,
            **known,
            segment_count=len(segs),
            latest_t=segs[-1].t if segs else 0.0,
        )

    # ---- 段落 ----
    async def append(self, session_id: str, segment: Segment) -> None:
        self._segments.setdefault(session_id, []).append(segment)
        if session_id in self._meta:
            self._meta[session_id]["updated_at"] = time.time()

    async def latest_t(self, session_id: str) -> float:
        segs = self._segments.get(session_id)
        return segs[-1].t if segs else 0.0

    async def window(self, session_id: str, start_t: float, end_t: float) -> list[Segment]:
        segs = self._segments.get(session_id, [])
        return [s for s in segs if start_t <= s.t <= end_t]

    async def all_segments(self, session_id: str) -> list[Segment]:
        return list(self._segments.get(session_id, []))

    # ---- 卡片 ----
    async def add_card(self, session_id: str, card: Card) -> None:
        self._cards.setdefault(session_id, []).append(card)

    async def list_cards(self, session_id: str) -> list[Card]:
        return sorted(self._cards.get(session_id, []), key=lambda c: c.index)

    async def card_count(self, session_id: str) -> int:
        return len(self._cards.get(session_id, []))

    # ---- 用户偏好 ----
    async def get_prefs(self, user_id: str) -> UserPrefs | None:
        return self._prefs.get(user_id)

    async def save_prefs(self, user_id: str, prefs: UserPrefs) -> None:
        self._prefs[user_id] = prefs
