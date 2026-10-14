"""登录与会话：Google Sign-In（ID token 校验）+ HMAC 签名的会话 cookie。

流程：前端用 Google Identity Services 拿到 ID token → POST /api/auth/google →
后端用 google-auth 校验 token（aud 必须是本项目的 client id）→ 下发签名 cookie。
之后每个 HTTP / WebSocket 请求都带 cookie，`current_user` 依赖负责解析。

本地开发（未配置 GOOGLE_CLIENT_ID 且不在 Cloud Run）允许 /api/auth/dev 直接登录为
一个固定的本地用户，方便不配 OAuth 也能跑通全流程。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import secrets
import time

from fastapi import Depends, HTTPException, Request, Response, WebSocket

from .config import Settings, get_settings
from .models import User

COOKIE_NAME = "lt_session"
DEV_USER = User(id="dev:local", email="dev@localhost", name="Local Dev")


# ---------------- cookie 签名 ----------------
_runtime_secret: bytes | None = None


def _secret(settings: Settings) -> bytes:
    """签名密钥：优先 SESSION_SECRET；没配就用进程内随机值（重启即失效）。"""
    global _runtime_secret
    if settings.session_secret:
        return settings.session_secret.encode("utf-8")
    if _runtime_secret is None:
        _runtime_secret = secrets.token_bytes(32)
    return _runtime_secret


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign_session(user: User, settings: Settings) -> str:
    payload = {**user.model_dump(), "exp": int(time.time()) + settings.session_days * 86400}
    body = _b64e(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    sig = hmac.new(_secret(settings), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64e(sig)}"


def verify_session(token: str | None, settings: Settings) -> User | None:
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    expect = hmac.new(_secret(settings), body.encode("ascii"), hashlib.sha256).digest()
    try:
        if not hmac.compare_digest(expect, _b64d(sig)):
            return None
        payload = json.loads(_b64d(body))
    except Exception:  # noqa: BLE001 - 任何解析失败都视为未登录
        return None
    if payload.get("exp", 0) < time.time():
        return None
    return User(**{k: payload.get(k, "") for k in User.model_fields})


def set_session_cookie(resp: Response, request: Request, user: User, settings: Settings) -> None:
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    resp.set_cookie(
        COOKIE_NAME, sign_session(user, settings),
        max_age=settings.session_days * 86400,
        httponly=True, samesite="lax", secure=secure, path="/",
    )


def clear_session_cookie(resp: Response) -> None:
    resp.delete_cookie(COOKIE_NAME, path="/")


# ---------------- Google ID token ----------------
async def verify_google_credential(credential: str, settings: Settings) -> User:
    """校验 Google Identity Services 返回的 ID token，返回用户信息。"""
    if not settings.google_client_id:
        raise HTTPException(status_code=503, detail="服务端未配置 GOOGLE_CLIENT_ID。")
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    def _verify() -> dict:
        return id_token.verify_oauth2_token(credential, google_requests.Request(), settings.google_client_id)

    try:
        info = await asyncio.to_thread(_verify)  # 同步 HTTP 取证书，放到线程里
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=f"Google 登录校验失败：{exc}") from exc
    if info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise HTTPException(status_code=401, detail="Google 登录校验失败：issuer 不合法。")
    email = (info.get("email") or "").lower()
    if settings.allowed_emails and (email not in settings.allowed_emails or not info.get("email_verified")):
        raise HTTPException(status_code=403, detail="このアカウントは許可されていません。")
    return User(
        id=f"google:{info['sub']}",
        email=email,
        name=info.get("name") or email,
        picture=info.get("picture", ""),
    )


# ---------------- FastAPI 依赖 ----------------
def optional_user(request: Request, settings: Settings = Depends(get_settings)) -> User | None:
    return verify_session(request.cookies.get(COOKIE_NAME), settings)


def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="未登录。")
    return user


def ws_user(ws: WebSocket, settings: Settings) -> User | None:
    """WebSocket 握手阶段同源会带 cookie，直接解析。"""
    return verify_session(ws.cookies.get(COOKIE_NAME), settings)
