"""非管理员用户的配额：单节课时长上限 + 每日新建课堂数上限 + 每日对话条数上限。

管理员（ADMIN_EMAILS）和本地开发用户不受限。配额数值全部来自 Settings，0 表示不限。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from .auth import DEV_USER
from .config import Settings
from .models import User
from .store import Store
from .usage import day_key


@dataclass(frozen=True)
class Limits:
    max_lecture_sec: float | None  # None = 不限
    max_lectures_per_day: int | None
    max_chats_per_day: int | None


def is_admin(user: User, settings: Settings) -> bool:
    """ADMIN_EMAILS 里的账号；没配任何管理员时，本地开发用户视为管理员（配了就按名单，便于本地测配额）。"""
    if user.id == DEV_USER.id and not settings.admin_emails:
        return True
    return user.email.lower() in settings.admin_emails


def limits_for(user: User, settings: Settings) -> Limits | None:
    """该用户的限制；管理员返回 None。"""
    if is_admin(user, settings):
        return None
    return Limits(
        max_lecture_sec=settings.quota_max_lecture_minutes * 60.0 or None,
        max_lectures_per_day=settings.quota_max_lectures_per_day or None,
        max_chats_per_day=settings.quota_max_chats_per_day or None,
    )


def lecture_cap_sec(user: User, settings: Settings) -> float | None:
    lim = limits_for(user, settings)
    return lim.max_lecture_sec if lim else None


async def lectures_today(store: Store, user: User, settings: Settings) -> int:
    tz = ZoneInfo(settings.quota_timezone)
    day_start = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    return sum(1 for s in await store.list_sessions(user.id) if s.created_at >= day_start)


async def check_can_create_lecture(store: Store, user: User, settings: Settings) -> None:
    """超出每日上限时抛 429；detail 用结构化 code，前端按界面语言翻译。"""
    lim = limits_for(user, settings)
    if lim is None or lim.max_lectures_per_day is None:
        return
    used = await lectures_today(store, user, settings)
    if used >= lim.max_lectures_per_day:
        raise HTTPException(
            status_code=429,
            detail={"code": "quota_lectures_per_day", "limit": lim.max_lectures_per_day, "used": used},
        )


async def chats_today(store: Store, user: User, settings: Settings) -> int:
    """今天成功完成的对话条数（失败的不计，见 routes/ai.py）。"""
    return int((await store.day_usage(user.id, day_key(settings))).get("chats", 0))


async def check_can_chat(store: Store, user: User, settings: Settings) -> None:
    lim = limits_for(user, settings)
    if lim is None or lim.max_chats_per_day is None:
        return
    used = await chats_today(store, user, settings)
    if used >= lim.max_chats_per_day:
        raise HTTPException(
            status_code=429,
            detail={"code": "quota_chats_per_day", "limit": lim.max_chats_per_day, "used": used},
        )


async def status(store: Store, user: User, settings: Settings) -> dict | None:
    """给前端展示用：None = 不受限。"""
    lim = limits_for(user, settings)
    if lim is None:
        return None
    return {
        "max_lecture_minutes": settings.quota_max_lecture_minutes or None,
        "max_lectures_per_day": lim.max_lectures_per_day,
        "lectures_today": await lectures_today(store, user, settings),
        "max_chats_per_day": lim.max_chats_per_day,
        "chats_today": await chats_today(store, user, settings),
    }
