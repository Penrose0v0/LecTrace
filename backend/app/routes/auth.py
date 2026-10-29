"""登录 / 登出 / 当前用户 / 偏好 / 域名迁移（handoff）。

域名迁移流程（PRIMARY_HOST 配了才启用）：
  旧域名页面（已登录） → POST /api/auth/handoff {next} → 返回新域名的 /auth/handoff?t=票据&next=…
  浏览器跳过去 → GET /auth/handoff 事务兑换票据 → 给新域名下发同内容的 cookie → 302 到 next
  失败（过期 / 用过 / host 不符）→ 302 /?handoff=expired，前端显示提示，用户正常走 Google 登录。
旧域名的 cookie 不动：两边各自保持登录，各自登出。
"""

from __future__ import annotations

import logging
import time
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from ..auth import (
    COOKIE_NAME,
    DEV_USER,
    clear_session_cookie,
    current_user,
    hash_handoff_ticket,
    is_legacy_host,
    is_primary_host,
    new_handoff_ticket,
    optional_user,
    public_host,
    safe_next,
    session_issued_at,
    set_session_cookie,
    verify_google_credential,
)
from .. import quota, usage
from ..config import Settings, get_settings
from ..deps import get_store, load_prefs
from ..models import LANGS, GoogleLoginRequest, User, UserPrefs

log = logging.getLogger("lectrace.auth")
router = APIRouter(prefix="/api", tags=["auth"])
# 顶层导航用的兑换路由（不在 /api 下）。main.py 里和其它路由一起在静态挂载之前注册
handoff_router = APIRouter(tags=["auth"])
_NO_STORE = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}


async def _login_payload(user: User, settings: Settings, *, login: bool) -> dict:
    store = get_store()
    await usage.record_login(store, user, settings, login=login)
    saved = await store.get_prefs(user.id)
    return {
        "user": user.model_dump(),
        "prefs": (saved or await load_prefs(user, settings)).model_dump(),
        # False = 服务端没存过（新用户，或本地内存后端重启丢了）；前端据此用浏览器语言 / 本地缓存补上
        "prefs_saved": saved is not None,
        "quota": await quota.status(store, user, settings),
    }


@router.get("/auth/config")
def auth_config(request: Request, settings: Settings = Depends(get_settings)) -> dict:
    """前端据此决定渲染 Google 按钮还是本地开发登录；以及当前是否在旧域名上（要不要迁移）。"""
    host = public_host(request, settings)
    return {
        "google_client_id": settings.google_client_id,
        "dev_login": settings.auth_dev_login,
        # 功能关闭时 primary_origin 为空、is_legacy 为 False，前端什么都不做
        "primary_origin": f"https://{settings.primary_host}" if settings.handoff_enabled else "",
        "is_legacy": is_legacy_host(host, settings),
        # 后端认定的公开域名（经 Worker 且密钥正确时是 X-Forwarded-Host，否则是 Host）。排查 Worker 配置用
        "host": host,
    }


class HandoffRequest(BaseModel):
    next: str = "/"


@router.post("/auth/handoff")
async def auth_handoff_create(
    req: HandoffRequest, request: Request, user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> Response:
    """旧域名上已登录的用户申请迁移票据。只在旧域名有效；新域名或功能关闭时 404。"""
    host = public_host(request, settings)
    if not is_legacy_host(host, settings):
        raise HTTPException(status_code=404)
    # 用户在任一域名登出过之后，旧域名上登出前签发的 cookie 不能再换票据：
    # 否则新域名登出 → 打开旧链接 → 又被自动登录。403 让前端不带票据跳过去，正常看登录页
    store = get_store()
    if session_issued_at(request.cookies.get(COOKIE_NAME)) < await store.logged_out_at(user.id):
        log.info("handoff refused for %s: cookie predates logout", user.id)
        raise HTTPException(status_code=403, detail={"code": "logged_out"})
    token, ticket_hash = new_handoff_ticket()
    now = time.time()
    await store.create_handoff(
        ticket_hash,
        {"user": user.model_dump(), "target": settings.primary_host, "from": host, "created_at": now},
        expires_at=now + settings.handoff_ttl_sec,
    )
    log.info("handoff created for %s from %s", user.id, host)
    qs = urlencode({"t": token, "next": safe_next(req.next)})
    return JSONResponse({"url": f"https://{settings.primary_host}/auth/handoff?{qs}"}, headers=_NO_STORE)


@handoff_router.get("/auth/handoff")
async def auth_handoff_redeem(
    request: Request, t: str = "", next: str = "/", settings: Settings = Depends(get_settings)
) -> Response:
    """新域名上兑换票据：成功下发本域名 cookie 并跳到 next；失败跳登录页并带 handoff=expired。"""
    host = public_host(request, settings)
    if not is_primary_host(host, settings):
        raise HTTPException(status_code=404)
    target = safe_next(next)
    failed = RedirectResponse("/?handoff=expired", status_code=302, headers=_NO_STORE)
    if not t or len(t) > 128:
        return failed
    data = await get_store().redeem_handoff(hash_handoff_ticket(t), time.time())
    if not data or data.get("target") != host:
        log.info("handoff rejected on %s (%s)", host, "no ticket" if not data else "wrong target")
        return failed
    try:
        user = User(**data["user"])
    except Exception:  # noqa: BLE001 - 票据数据损坏也按失败处理
        return failed
    resp = RedirectResponse(target, status_code=302, headers=_NO_STORE)
    set_session_cookie(resp, request, user, settings)
    await usage.record_login(get_store(), user, settings, login=False)
    log.info("handoff redeemed for %s on %s", user.id, host)
    return resp


@router.post("/auth/google")
async def auth_google(
    req: GoogleLoginRequest, request: Request, response: Response,
    settings: Settings = Depends(get_settings),
) -> dict:
    user = await verify_google_credential(req.credential, settings)
    set_session_cookie(response, request, user, settings)
    return await _login_payload(user, settings, login=True)


@router.post("/auth/dev")
async def auth_dev(
    request: Request, response: Response, settings: Settings = Depends(get_settings)
) -> dict:
    if not settings.auth_dev_login:
        raise HTTPException(status_code=403, detail="本地开发登录未开启。")
    set_session_cookie(response, request, DEV_USER, settings)
    return await _login_payload(DEV_USER, settings, login=True)


@router.post("/auth/logout")
async def auth_logout(response: Response, user: User | None = Depends(optional_user)) -> dict:
    clear_session_cookie(response)
    if user is not None:
        # 记下登出时间：另一个域名上更早签发的 cookie 从此不能再换迁移票据（见 auth_handoff_create）
        try:
            await get_store().mark_logout(user.id, time.time())
        except Exception:  # noqa: BLE001 - 记不上也要让用户登出
            log.exception("mark_logout failed")
    return {"ok": True}


@router.get("/auth/me")
async def auth_me(
    user: User | None = Depends(optional_user), settings: Settings = Depends(get_settings)
) -> dict:
    if user is None:
        return {"user": None}
    return await _login_payload(user, settings, login=False)  # 刷新页面：只更新 last_seen


@router.put("/me/prefs")
async def save_prefs(prefs: UserPrefs, user: User = Depends(current_user)) -> dict:
    if prefs.ui_language not in LANGS or prefs.lecture_language not in LANGS:
        raise HTTPException(status_code=400, detail="不支持的语言。")
    await get_store().save_prefs(user.id, prefs)
    return prefs.model_dump()
