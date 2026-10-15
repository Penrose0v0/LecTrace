"""管理后台 API（仅 ADMIN_EMAILS）：每个用户的登录、转录时长、对话次数、token 与估算成本。

页面在 frontend/admin.html（同一个登录 cookie）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import quota
from ..auth import current_user
from ..config import Settings, get_settings
from ..deps import get_store
from ..models import User
from ..usage import USAGE_FIELDS, day_key

router = APIRouter(prefix="/api/admin", tags=["admin"])


def admin_user(user: User = Depends(current_user), settings: Settings = Depends(get_settings)) -> User:
    if not quota.is_admin(user, settings):
        raise HTTPException(status_code=403, detail="仅管理员可访问。")
    return user


def _fill(u: dict) -> dict:
    """usage 缺的字段补 0，前端省得判空。"""
    return {k: u.get(k, 0) for k in USAGE_FIELDS}


@router.get("/users")
async def list_users(_: User = Depends(admin_user), settings: Settings = Depends(get_settings)) -> dict:
    users = await get_store().list_users()
    for u in users:
        u["usage"] = _fill(u.get("usage") or {})
        u["is_admin"] = (u.get("email") or "").lower() in settings.admin_emails
    totals = {k: sum(u["usage"][k] for u in users) for k in USAGE_FIELDS}
    return {
        "users": users,
        "totals": totals,
        "today": day_key(settings),
        "currency": settings.cost_currency,
        "pricing": {
            "llm_input_per_m": settings.llm_price_input_per_m,
            "llm_output_per_m": settings.llm_price_output_per_m,
            "stt_per_min": settings.stt_price_per_min,
            "llm_model": settings.llm_model,
        },
        "quota": {
            "max_lecture_minutes": settings.quota_max_lecture_minutes or None,
            "max_lectures_per_day": settings.quota_max_lectures_per_day or None,
            "max_chats_per_day": settings.quota_max_chats_per_day or None,
        },
    }


@router.get("/users/{user_id}")
async def user_detail(
    user_id: str,
    _: User = Depends(admin_user),
    days: int = Query(default=30, ge=1, le=366),
    events: int = Query(default=50, ge=0, le=500),
) -> dict:
    store = get_store()
    return {
        "days": [{**_fill(d), "day": d.get("day", "")} for d in await store.list_user_days(user_id, days)],
        "events": await store.list_user_events(user_id, events) if events else [],
    }
