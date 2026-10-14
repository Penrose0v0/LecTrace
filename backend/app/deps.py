"""各路由共用的单例与依赖：settings / store / 「本人的讲义」。"""

from __future__ import annotations

import json
from functools import lru_cache

from fastapi import Depends, HTTPException

from .auth import current_user
from .config import Settings, get_settings
from .models import SessionInfo, User, UserPrefs
from .store import Store, make_store


@lru_cache
def get_store() -> Store:
    return make_store(get_settings())


async def owned_session(session_id: str, user: User = Depends(current_user)) -> SessionInfo:
    """路径参数 session_id 对应的讲义，且必须属于当前用户。"""
    info = await get_store().get_session(session_id)
    if info is None:
        raise HTTPException(status_code=404, detail="讲义不存在。")
    if info.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权访问这节课。")
    return info


async def load_prefs(user: User, settings: Settings) -> UserPrefs:
    """用户偏好；没存过就用环境变量里的默认语言。"""
    prefs = await get_store().get_prefs(user.id)
    return prefs or UserPrefs(ui_language=settings.user_language, lecture_language=settings.lecture_language)


# ---------------- SSE ----------------
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def sse(event: str | None, data: dict) -> str:
    prefix = f"event: {event}\n" if event else ""
    return f"{prefix}data: {json.dumps(data, ensure_ascii=False)}\n\n"
