"""转录 / 卡片存储的可插拔抽象。

STORE_BACKEND=memory（默认，进程内）或 firestore（持久化）。
两种后端实现同一个 TranscriptStore 接口，上层代码不变。
"""

from __future__ import annotations

from ..config import get_settings
from .base import TranscriptStore
from .memory import MemoryStore

_store: TranscriptStore | None = None


def get_store() -> TranscriptStore:
    global _store
    if _store is None:
        settings = get_settings()
        backend = settings.store_backend
        if backend == "memory":
            _store = MemoryStore()
        elif backend == "firestore":
            from .firestore import FirestoreStore

            _store = FirestoreStore(
                project=settings.gcp_project or None,
                database=settings.firestore_database,
            )
        else:
            raise ValueError(f"未知 STORE_BACKEND: {backend}")
    return _store


__all__ = ["TranscriptStore", "get_store"]
