"""转录存储的可插拔抽象。

demo 用内存实现；之后加 FirestoreStore 时只需实现同一个 TranscriptStore 接口，
main.py 按 STORE_BACKEND 选择，其余代码不动。
"""

from __future__ import annotations

from ..config import get_settings
from .base import TranscriptStore
from .memory import MemoryStore

_store: TranscriptStore | None = None


def get_store() -> TranscriptStore:
    global _store
    if _store is None:
        backend = get_settings().store_backend
        if backend == "memory":
            _store = MemoryStore()
        else:  # pragma: no cover - firestore 尚未接入
            raise NotImplementedError(f"store backend 未实现: {backend}")
    return _store


__all__ = ["TranscriptStore", "get_store"]
