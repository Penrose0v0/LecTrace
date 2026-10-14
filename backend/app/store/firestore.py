"""Firestore 版存储：讲义会话 + 转录段落 + Catchup 卡片 + 用户偏好。

数据模型：
  sessions/{session_id}
    ├─ (doc fields) user_id, title, description, lecture_language, user_language,
    │               window_minutes, source, file, created_at, updated_at,
    │               segment_count, latest_t   ← 后两个随 append 原子更新，列表页免遍历
    ├─ segments/{seq}   {seq, text, t}
    └─ cards/{card_id}  {index, covered_from, covered_to, segment_count,
                         model, lecture_language, user_language, summary, created_t}
  users/{user_id}       {ui_language, lecture_language, window_minutes, theme}

用 AsyncClient，全程 await，不阻塞事件循环。设置 FIRESTORE_EMULATOR_HOST 即连模拟器。
list_sessions 只按 user_id 过滤、在内存里排序，避免 Firestore 组合索引。
"""

from __future__ import annotations

import time

from google.cloud import firestore

from ..models import Card, Segment, SessionInfo, UserPrefs


class FirestoreStore:
    def __init__(self, project: str | None = None, database: str = "(default)") -> None:
        kwargs: dict = {"database": database}
        if project:
            kwargs["project"] = project
        self._db = firestore.AsyncClient(**kwargs)

    def _session(self, session_id: str):
        return self._db.collection("sessions").document(session_id)

    # ---- 会话 ----
    async def create_session(self, session_id: str, meta: dict | None = None) -> None:
        now = time.time()
        data = {
            "created_at": now,
            "updated_at": now,
            "segment_count": 0,
            "latest_t": 0.0,
            **(meta or {}),
        }
        await self._session(session_id).set(data, merge=True)

    async def get_session(self, session_id: str) -> SessionInfo | None:
        snap = await self._session(session_id).get()
        if not snap.exists:
            return None
        return self._info(snap.id, snap.to_dict() or {})

    async def update_session(self, session_id: str, patch: dict) -> None:
        await self._session(session_id).set({**patch, "updated_at": time.time()}, merge=True)

    async def list_sessions(self, user_id: str) -> list[SessionInfo]:
        q = self._db.collection("sessions").where(
            filter=firestore.FieldFilter("user_id", "==", user_id)
        )
        out: list[SessionInfo] = []
        async for snap in q.stream():
            out.append(self._info(snap.id, snap.to_dict() or {}))
        out.sort(key=lambda s: s.created_at, reverse=True)
        return out

    @staticmethod
    def _info(session_id: str, d: dict) -> SessionInfo:
        known = {k: v for k, v in d.items() if k in SessionInfo.model_fields and k != "id"}
        # 旧数据 created_at 可能是 SERVER_TIMESTAMP（datetime）
        ca = known.get("created_at")
        if hasattr(ca, "timestamp"):
            known["created_at"] = ca.timestamp()
        return SessionInfo(id=session_id, **known)

    # ---- 段落 ----
    async def append(self, session_id: str, segment: Segment) -> None:
        batch = self._db.batch()
        batch.set(
            self._session(session_id).collection("segments").document(str(segment.seq)),
            {"seq": segment.seq, "text": segment.text, "t": segment.t},
        )
        batch.set(
            self._session(session_id),
            {
                "segment_count": firestore.Increment(1),
                "latest_t": segment.t,
                "updated_at": time.time(),
            },
            merge=True,
        )
        await batch.commit()

    async def latest_t(self, session_id: str) -> float:
        segs = self._session(session_id).collection("segments")
        q = segs.order_by("t", direction=firestore.Query.DESCENDING).limit(1)
        async for doc in q.stream():
            return float(doc.get("t"))
        return 0.0

    async def window(self, session_id: str, start_t: float, end_t: float) -> list[Segment]:
        segs = self._session(session_id).collection("segments")
        q = (
            segs.where(filter=firestore.FieldFilter("t", ">=", start_t))
            .where(filter=firestore.FieldFilter("t", "<=", end_t))
            .order_by("t")
        )
        out: list[Segment] = []
        async for doc in q.stream():
            d = doc.to_dict()
            out.append(Segment(seq=d["seq"], text=d["text"], t=d["t"]))
        return out

    async def all_segments(self, session_id: str) -> list[Segment]:
        segs = self._session(session_id).collection("segments").order_by("t")
        out: list[Segment] = []
        async for doc in segs.stream():
            d = doc.to_dict()
            out.append(Segment(seq=d["seq"], text=d["text"], t=d["t"]))
        return out

    # ---- 卡片 ----
    async def add_card(self, session_id: str, card: Card) -> None:
        await self._session(session_id).collection("cards").document(card.id).set(
            {
                "index": card.index,
                "covered_from": card.covered_from,
                "covered_to": card.covered_to,
                "segment_count": card.segment_count,
                "model": card.model,
                "lecture_language": card.lecture_language,
                "user_language": card.user_language,
                "summary": card.summary,
                "created_t": card.created_t,
            }
        )

    async def list_cards(self, session_id: str) -> list[Card]:
        cards = self._session(session_id).collection("cards").order_by("index")
        out: list[Card] = []
        async for doc in cards.stream():
            d = doc.to_dict()
            out.append(Card(id=doc.id, **d))
        return out

    async def card_count(self, session_id: str) -> int:
        # 卡片数量很小，直接数
        count = 0
        async for _ in self._session(session_id).collection("cards").stream():
            count += 1
        return count

    # ---- 用户偏好 ----
    async def get_prefs(self, user_id: str) -> UserPrefs | None:
        snap = await self._db.collection("users").document(user_id).get()
        if not snap.exists:
            return None
        return UserPrefs(**{k: v for k, v in (snap.to_dict() or {}).items() if k in UserPrefs.model_fields})

    async def save_prefs(self, user_id: str, prefs: UserPrefs) -> None:
        await self._db.collection("users").document(user_id).set(prefs.model_dump(), merge=True)
