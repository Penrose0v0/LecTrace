"""按用户记用量：登录、转录时长、LLM token 与估算成本。

数据（见 store）：
  users/{uid}             资料 + 累计 usage
  users/{uid}/days/{day}  按 QUOTA_TIMEZONE 自然日的 usage（配额计数也从这里读）
  users/{uid}/events/{id} 每次 LLM 调用 / 每段转录连接的明细

usage 字段都是累加数：
  logins, lectures, stt_seconds（v1 / OpenAI）, stt_v2_seconds（Google v2）, stt_cost, catchups, chats,
  llm_calls, llm_in_tokens, llm_out_tokens, llm_cost
成本按 .env 里的单价估算（LLM_PRICE_*、STT_PRICE_PER_MIN、STT_V2_PRICE_PER_MIN），没配就是 0；货币只是个标签。
后台展示时按当前单价由 token / 秒数重算（routes/admin.py），这里存的 cost 只是记录当时的值。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from .config import Settings
from .llm.base import LLMUsage
from .models import User
from .store import Store

log = logging.getLogger("lectrace.usage")

USAGE_FIELDS = (
    "logins", "lectures", "stt_seconds", "stt_v2_seconds", "stt_cost",
    "catchups", "chats", "llm_calls", "llm_in_tokens", "llm_out_tokens", "llm_cost",
)


def stt_seconds_field(source: str) -> str:
    return "stt_v2_seconds" if source == "google-stt-v2" else "stt_seconds"


def stt_price_per_min(source: str, settings: Settings) -> float:
    return settings.stt_v2_price_per_min if source == "google-stt-v2" else settings.stt_price_per_min


def day_key(settings: Settings, ts: float | None = None) -> str:
    """配额 / 日统计用的日期键（YYYY-MM-DD，按 QUOTA_TIMEZONE）。"""
    tz = ZoneInfo(settings.quota_timezone)
    return datetime.fromtimestamp(ts if ts is not None else time.time(), tz).strftime("%Y-%m-%d")


def llm_cost(usage: LLMUsage, settings: Settings) -> float:
    return (
        usage.input_tokens * settings.llm_price_input_per_m
        + usage.output_tokens * settings.llm_price_output_per_m
    ) / 1_000_000


def stt_cost(seconds: float, source: str, settings: Settings) -> float:
    return seconds / 60.0 * stt_price_per_min(source, settings)


async def _add(store: Store, user_id: str, settings: Settings, fields: dict, event: dict | None) -> None:
    """记用量失败只记日志，绝不影响主流程。"""
    try:
        await store.add_usage(user_id, day_key(settings), fields)
        if event is not None:
            await store.add_event(user_id, {"ts": time.time(), **event})
    except Exception:  # noqa: BLE001
        log.exception("record usage failed")


async def record_login(store: Store, user: User, settings: Settings, *, login: bool) -> None:
    """login=True 是真正登录；False 只是刷新了页面（更新 last_seen）。"""
    try:
        await store.touch_user(user, login=login)
        if login:
            await store.add_usage(user.id, day_key(settings), {"logins": 1})
    except Exception:  # noqa: BLE001
        log.exception("record login failed")


async def record_lecture(store: Store, user: User, settings: Settings, session_id: str) -> None:
    await _add(store, user.id, settings, {"lectures": 1}, None)


async def record_stt(
    store: Store, user: User, settings: Settings, session_id: str, seconds: float, source: str
) -> None:
    if seconds <= 0:
        return
    cost = stt_cost(seconds, source, settings)
    await _add(
        store, user.id, settings,
        {stt_seconds_field(source): seconds, "stt_cost": cost},
        {"kind": "stt", "session_id": session_id, "source": source, "seconds": round(seconds, 1), "cost": cost},
    )


async def record_llm(
    store: Store, user: User, settings: Settings, session_id: str, kind: str, usage: LLMUsage, elapsed: float
) -> None:
    """kind = catchup | chat。"""
    cost = llm_cost(usage, settings)
    await _add(
        store, user.id, settings,
        {
            f"{kind}s": 1, "llm_calls": 1,
            "llm_in_tokens": usage.input_tokens, "llm_out_tokens": usage.output_tokens, "llm_cost": cost,
        },
        {
            "kind": kind, "session_id": session_id, "model": settings.llm_model,
            "in_tokens": usage.input_tokens, "out_tokens": usage.output_tokens, "cost": cost,
            "elapsed_ms": int(elapsed * 1000),
        },
    )
