"""登录 / 登出 / 当前用户 / 偏好。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..auth import (
    DEV_USER,
    clear_session_cookie,
    current_user,
    optional_user,
    set_session_cookie,
    verify_google_credential,
)
from ..config import Settings, get_settings
from ..deps import get_store, load_prefs
from ..models import LANGS, GoogleLoginRequest, User, UserPrefs

router = APIRouter(prefix="/api", tags=["auth"])


async def _login_payload(user: User, settings: Settings) -> dict:
    return {"user": user.model_dump(), "prefs": (await load_prefs(user, settings)).model_dump()}


@router.get("/auth/config")
def auth_config(settings: Settings = Depends(get_settings)) -> dict:
    """前端据此决定渲染 Google 按钮还是本地开发登录。"""
    return {"google_client_id": settings.google_client_id, "dev_login": settings.auth_dev_login}


@router.post("/auth/google")
async def auth_google(
    req: GoogleLoginRequest, request: Request, response: Response,
    settings: Settings = Depends(get_settings),
) -> dict:
    user = await verify_google_credential(req.credential, settings)
    set_session_cookie(response, request, user, settings)
    return await _login_payload(user, settings)


@router.post("/auth/dev")
async def auth_dev(
    request: Request, response: Response, settings: Settings = Depends(get_settings)
) -> dict:
    if not settings.auth_dev_login:
        raise HTTPException(status_code=403, detail="本地开发登录未开启。")
    set_session_cookie(response, request, DEV_USER, settings)
    return await _login_payload(DEV_USER, settings)


@router.post("/auth/logout")
def auth_logout(response: Response) -> dict:
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/auth/me")
async def auth_me(
    user: User | None = Depends(optional_user), settings: Settings = Depends(get_settings)
) -> dict:
    if user is None:
        return {"user": None}
    return await _login_payload(user, settings)


@router.put("/me/prefs")
async def save_prefs(prefs: UserPrefs, user: User = Depends(current_user)) -> dict:
    if prefs.ui_language not in LANGS or prefs.lecture_language not in LANGS:
        raise HTTPException(status_code=400, detail="不支持的语言。")
    await get_store().save_prefs(user.id, prefs)
    return prefs.model_dump()
