"""存储（可插拔）：STORE_BACKEND=memory（默认，进程内）| firestore（持久化）。"""

from __future__ import annotations

from ..config import Settings
from .base import Store


def make_store(settings: Settings) -> Store:
    if settings.store_backend == "memory":
        from .memory import MemoryStore

        return MemoryStore()
    if settings.store_backend == "firestore":
        from .firestore import FirestoreStore

        return FirestoreStore(project=settings.gcp_project or None, database=settings.firestore_database)
    raise ValueError(f"未知 STORE_BACKEND: {settings.store_backend}")


__all__ = ["Store", "make_store"]
