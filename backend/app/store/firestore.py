"""Firestore 版存储。

数据模型：
  sessions/{session_id}
    ├─ (doc fields) user_id + LectureMeta 字段 + created_at, updated_at,
    │               segment_count, latest_t   ← 后两个随 append 原子更新，列表页免遍历
    ├─ segments/{seq}   {seq, text, t}
    └─ cards/{card_id}  Card 字段
  conversations/{id}    {session_id, title, created_t, messages: [...]}
  users/{user_id}       UserPrefs 字段

用 AsyncClient，全程 await。设置 FIRESTORE_EMULATOR_HOST 即连模拟器。
按 user_id / session_id 的列表查询都只过滤、在内存里排序，避免 Firestore 组合索引。
"""

from __future__ import annotations

import time
import uuid

from google.cloud import firestore

from ..models import Card, Conversation, Segment, SessionInfo, UserPrefs


class FirestoreStore:
    def __init__(self, project: str | None = None, database: str = "(default)") -> None:
        kwargs: dict = {"database": database}
        if project:
            kwargs["project"] = project
        self._db = firestore.AsyncClient(**kwargs)

    def _session(self, session_id: str):
        return self._db.collection("sessions").document(session_id)

    def _conv(self, cid: str):
        return self._db.collection("conversations").document(cid)

    # ---- 会话 ----
    async def create_session(self, session_id: str, meta: dict) -> None:
        now = time.time()
        data = {"created_at": now, "updated_at": now, "segment_count": 0, "latest_t": 0.0, **meta}
        await self._session(session_id).set(data, merge=True)

    async def get_session(self, session_id: str) -> SessionInfo | None:
        snap = await self._session(session_id).get()
        return self._info(snap.id, snap.to_dict() or {}) if snap.exists else None

    async def update_session(self, session_id: str, patch: dict) -> None:
        await self._session(session_id).set({**patch, "updated_at": time.time()}, merge=True)

    async def list_sessions(self, user_id: str) -> list[SessionInfo]:
        q = self._db.collection("sessions").where(filter=firestore.FieldFilter("user_id", "==", user_id))
        out = [self._info(snap.id, snap.to_dict() or {}) async for snap in q.stream()]
        out.sort(key=lambda s: s.created_at, reverse=True)
        return out

    @staticmethod
    def _info(session_id: str, d: dict) -> SessionInfo:
        known = {k: v for k, v in d.items() if k in SessionInfo.model_fields and k != "id"}
        ca = known.get("created_at")
        if hasattr(ca, "timestamp"):  # 旧数据 created_at 是 SERVER_TIMESTAMP（datetime）
            known["created_at"] = ca.timestamp()
        return SessionInfo(id=session_id, **known)

    # ---- 段落 ----
    async def append(self, session_id: str, segment: Segment) -> None:
        batch = self._db.batch()
        batch.set(
            self._session(session_id).collection("segments").document(str(segment.seq)),
            segment.model_dump(),
        )
        batch.set(
            self._session(session_id),
            {"segment_count": firestore.Increment(1), "latest_t": segment.t, "updated_at": time.time()},
            merge=True,
        )
        await batch.commit()

    async def all_segments(self, session_id: str) -> list[Segment]:
        q = self._session(session_id).collection("segments").order_by("t")
        return [Segment(**doc.to_dict()) async for doc in q.stream()]

    async def latest_t(self, session_id: str) -> float:
        q = (
            self._session(session_id)
            .collection("segments")
            .order_by("t", direction=firestore.Query.DESCENDING)
            .limit(1)
        )
        async for doc in q.stream():
            return float(doc.get("t"))
        return 0.0

    async def window(self, session_id: str, start_t: float, end_t: float) -> list[Segment]:
        q = (
            self._session(session_id)
            .collection("segments")
            .where(filter=firestore.FieldFilter("t", ">=", start_t))
            .where(filter=firestore.FieldFilter("t", "<=", end_t))
            .order_by("t")
        )
        return [Segment(**doc.to_dict()) async for doc in q.stream()]

    # ---- 卡片 ----
    async def add_card(self, session_id: str, card: Card) -> None:
        await self._session(session_id).collection("cards").document(card.id).set(
            card.model_dump(exclude={"id"})
        )

    async def list_cards(self, session_id: str) -> list[Card]:
        q = self._session(session_id).collection("cards").order_by("index")
        return [Card(id=doc.id, **doc.to_dict()) async for doc in q.stream()]

    async def card_count(self, session_id: str) -> int:
        agg = await self._session(session_id).collection("cards").count().get()
        return int(agg[0][0].value)

    # ---- 对话 ----
    async def create_conversation(self, session_id: str, title: str, created_t: float) -> Conversation:
        conv = Conversation(id=uuid.uuid4().hex, session_id=session_id, title=title, created_t=created_t)
        await self._conv(conv.id).set(conv.model_dump(exclude={"id"}))
        return conv

    async def get_conversation(self, cid: str) -> Conversation | None:
        snap = await self._conv(cid).get()
        return Conversation(id=cid, **snap.to_dict()) if snap.exists else None

    async def list_conversations(self, session_id: str) -> list[Conversation]:
        q = self._db.collection("conversations").where(
            filter=firestore.FieldFilter("session_id", "==", session_id)
        )
        out = [Conversation(id=snap.id, **snap.to_dict()) async for snap in q.stream()]
        out.sort(key=lambda c: c.created_t, reverse=True)
        return out

    async def save_conversation(self, conv: Conversation) -> None:
        await self._conv(conv.id).set(conv.model_dump(exclude={"id"}))

    # ---- 用户偏好 ----
    async def get_prefs(self, user_id: str) -> UserPrefs | None:
        snap = await self._db.collection("users").document(user_id).get()
        if not snap.exists:
            return None
        d = snap.to_dict() or {}
        return UserPrefs(**{k: v for k, v in d.items() if k in UserPrefs.model_fields})

    async def save_prefs(self, user_id: str, prefs: UserPrefs) -> None:
        await self._db.collection("users").document(user_id).set(prefs.model_dump(), merge=True)
