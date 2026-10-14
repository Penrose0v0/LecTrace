"""AI 对话的持久化存储（内存 / Firestore 可插拔）。

Firestore 数据模型：
  conversations/{id}  {session_id, title, created_t, messages: [{role, content}, ...]}
"""

from __future__ import annotations

import uuid
from typing import Protocol

from .config import get_settings


class Conversation:
    def __init__(self, cid: str, session_id: str, title: str, created_t: float) -> None:
        self.id = cid
        self.session_id = session_id
        self.title = title
        self.created_t = created_t
        # [{"role": "user"|"assistant", "content": str, ...}]
        # Catch-up 摘要也存在这里：kind="catchup" + covered_from/covered_to/segment_count
        self.messages: list[dict] = []

    def summary(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "created_t": self.created_t,
            "message_count": len(self.messages),
        }


class ConversationStore(Protocol):
    async def create(self, session_id: str, title: str, created_t: float) -> Conversation: ...
    async def get(self, cid: str) -> Conversation | None: ...
    async def list(self, session_id: str) -> list[Conversation]: ...
    async def save(self, conv: Conversation) -> None: ...


class MemoryConversationStore:
    def __init__(self) -> None:
        self._c: dict[str, Conversation] = {}

    async def create(self, session_id: str, title: str, created_t: float) -> Conversation:
        cid = uuid.uuid4().hex
        conv = Conversation(cid, session_id, title, created_t)
        self._c[cid] = conv
        return conv

    async def get(self, cid: str) -> Conversation | None:
        return self._c.get(cid)

    async def list(self, session_id: str) -> list[Conversation]:
        return [c for c in self._c.values() if c.session_id == session_id]

    async def save(self, conv: Conversation) -> None:
        # 内存里 get 返回的就是同一对象，改动已生效
        self._c[conv.id] = conv


class FirestoreConversationStore:
    def __init__(self, project: str | None = None, database: str = "(default)") -> None:
        from google.cloud import firestore

        kwargs: dict = {"database": database}
        if project:
            kwargs["project"] = project
        self._db = firestore.AsyncClient(**kwargs)

    def _doc(self, cid: str):
        return self._db.collection("conversations").document(cid)

    async def create(self, session_id: str, title: str, created_t: float) -> Conversation:
        cid = uuid.uuid4().hex
        conv = Conversation(cid, session_id, title, created_t)
        await self._doc(cid).set(
            {"session_id": session_id, "title": title, "created_t": created_t, "messages": []}
        )
        return conv

    async def get(self, cid: str) -> Conversation | None:
        snap = await self._doc(cid).get()
        if not snap.exists:
            return None
        d = snap.to_dict()
        conv = Conversation(cid, d["session_id"], d["title"], d.get("created_t", 0.0))
        conv.messages = d.get("messages", [])
        return conv

    async def list(self, session_id: str) -> list[Conversation]:
        from google.cloud import firestore

        q = self._db.collection("conversations").where(
            filter=firestore.FieldFilter("session_id", "==", session_id)
        )
        out: list[Conversation] = []
        async for snap in q.stream():
            d = snap.to_dict()
            conv = Conversation(snap.id, d["session_id"], d["title"], d.get("created_t", 0.0))
            conv.messages = d.get("messages", [])
            out.append(conv)
        return out

    async def save(self, conv: Conversation) -> None:
        await self._doc(conv.id).set(
            {
                "session_id": conv.session_id,
                "title": conv.title,
                "created_t": conv.created_t,
                "messages": conv.messages,
            }
        )


_store: ConversationStore | None = None


def get_conversation_store() -> ConversationStore:
    global _store
    if _store is None:
        settings = get_settings()
        if settings.store_backend == "firestore":
            _store = FirestoreConversationStore(
                project=settings.gcp_project or None,
                database=settings.firestore_database,
            )
        else:
            _store = MemoryConversationStore()
    return _store
