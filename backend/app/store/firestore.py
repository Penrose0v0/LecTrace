"""Firestore 版存储。

数据模型：
  sessions/{session_id}
    ├─ (doc fields) user_id + LectureMeta 字段 + created_at, updated_at,
    │               segment_count, latest_t   ← 后两个随 append 原子更新，列表页免遍历
    ├─ segments/{seq}   {seq, text, t}
    └─ cards/{card_id}  Card 字段
  conversations/{id}    {session_id, title, created_t, messages: [...]}
  users/{user_id}       UserPrefs 字段 + 资料（email, name, picture, first/last_login_at, last_seen_at,
    │                   login_count）+ usage: {累计用量，见 usage.py}
    ├─ days/{YYYY-MM-DD}  当日用量（同一组字段）
    └─ events/{id}        用量明细 {ts, kind, ...}
  handoff_tickets/{sha256}  域名迁移票据 {data, expires_at, used, ttl}
    ttl 是 Timestamp，供 Firestore TTL 策略自动清理（控制台对该集合启用 TTL、字段选 ttl）

用 AsyncClient，全程 await。设置 FIRESTORE_EMULATOR_HOST 即连模拟器。
按 user_id / session_id 的列表查询都只过滤、在内存里排序，避免 Firestore 组合索引。
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from google.cloud import firestore

from ..models import Card, Conversation, Segment, SessionInfo, User, UserPrefs

USER_PROFILE_FIELDS = (
    "email", "name", "picture", "first_login_at", "last_login_at", "last_seen_at", "login_count",
)


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

    async def add_recording(self, session_id: str, info: dict) -> None:
        await self._session(session_id).set(
            {"recordings": firestore.ArrayUnion([info]), "updated_at": time.time()}, merge=True
        )

    async def delete_session(self, session_id: str) -> None:
        sess = self._session(session_id)
        for sub in ("segments", "cards"):
            await self._delete_all(sess.collection(sub))
        convs = self._db.collection("conversations").where(
            filter=firestore.FieldFilter("session_id", "==", session_id)
        )
        await self._delete_all(convs)
        await sess.delete()

    async def _delete_all(self, query) -> None:
        """分批删掉查询结果（一批最多 500 次写）。"""
        batch, n = self._db.batch(), 0
        async for snap in query.stream():
            batch.delete(snap.reference)
            n += 1
            if n % 400 == 0:
                await batch.commit()
                batch = self._db.batch()
        if n % 400:
            await batch.commit()

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

    # ---- 用户资料 / 用量 ----
    def _user(self, user_id: str):
        return self._db.collection("users").document(user_id)

    async def touch_user(self, user: User, *, login: bool) -> None:
        now = time.time()
        data: dict = {"email": user.email, "name": user.name, "picture": user.picture, "last_seen_at": now}
        if login:
            data.update(last_login_at=now, login_count=firestore.Increment(1))
            # first_login_at 只在没有时写：merge 不支持“缺省才写”，先读一下
            snap = await self._user(user.id).get()
            if not snap.exists or "first_login_at" not in (snap.to_dict() or {}):
                data["first_login_at"] = now
        await self._user(user.id).set(data, merge=True)

    async def add_usage(self, user_id: str, day: str, fields: dict) -> None:
        inc = {k: firestore.Increment(v) for k, v in fields.items()}
        batch = self._db.batch()
        batch.set(self._user(user_id), {"usage": inc, "usage_updated_at": time.time()}, merge=True)
        batch.set(self._user(user_id).collection("days").document(day), {"day": day, **inc}, merge=True)
        await batch.commit()

    async def day_usage(self, user_id: str, day: str) -> dict:
        snap = await self._user(user_id).collection("days").document(day).get()
        return (snap.to_dict() or {}) if snap.exists else {}

    async def add_event(self, user_id: str, event: dict) -> None:
        await self._user(user_id).collection("events").document(uuid.uuid4().hex).set(event)

    async def list_users(self) -> list[dict]:
        out = []
        async for snap in self._db.collection("users").stream():
            d = snap.to_dict() or {}
            u = {k: d.get(k) for k in USER_PROFILE_FIELDS}
            out.append({"id": snap.id, **u, "usage": d.get("usage") or {}})
        out.sort(key=lambda u: u.get("last_seen_at") or 0, reverse=True)
        return out

    async def list_user_days(self, user_id: str, limit: int) -> list[dict]:
        # 按 day 字段倒序（单字段倒序有自动索引）。按 __name__ 倒序看似等价，但 Firestore 要求手建索引
        q = (
            self._user(user_id).collection("days")
            .order_by("day", direction=firestore.Query.DESCENDING)
            .limit(limit)
        )
        return [{"day": snap.id, **(snap.to_dict() or {})} async for snap in q.stream()]

    async def list_user_events(self, user_id: str, limit: int) -> list[dict]:
        q = (
            self._user(user_id).collection("events")
            .order_by("ts", direction=firestore.Query.DESCENDING)
            .limit(limit)
        )
        return [snap.to_dict() or {} async for snap in q.stream()]

    # ---- 域名迁移票据 ----
    def _handoff(self, ticket_hash: str):
        return self._db.collection("handoff_tickets").document(ticket_hash)

    async def create_handoff(self, ticket_hash: str, data: dict, expires_at: float) -> None:
        await self._handoff(ticket_hash).set({
            "data": data, "expires_at": expires_at, "used": False, "created_at": time.time(),
            # TTL 策略用：过期后再留 1 天给排查，之后自动删
            "ttl": datetime.fromtimestamp(expires_at + 86400, tz=timezone.utc),
        })

    async def redeem_handoff(self, ticket_hash: str, now: float) -> dict | None:
        ref = self._handoff(ticket_hash)

        @firestore.async_transactional
        async def _redeem(tx) -> dict | None:
            snap = await ref.get(transaction=tx)
            if not snap.exists:
                return None
            d = snap.to_dict() or {}
            if d.get("used") or float(d.get("expires_at", 0)) < now:
                return None
            tx.update(ref, {"used": True, "used_at": now})
            return dict(d.get("data") or {})

        # 事务保证并发兑换只有一个成功：第二个事务读到 used=True 返回 None，或因冲突重试后同样 None
        return await _redeem(self._db.transaction())
