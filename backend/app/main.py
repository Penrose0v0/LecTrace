"""LecTrace 后端入口：装配路由 + 前端静态托管。

路由分布：
  routes/auth.py        登录 / 登出 / 当前用户 / 偏好
  routes/lectures.py    讲义（session）增查改、归档列表、卡片与线程列表
  routes/ai.py          Catch-up 摘要、对话（SSE）
  routes/transcribe.py  转录 WebSocket（麦克风代理 STT / 回放）
  routes/admin.py       管理后台：按用户的用量 / 成本（仅 ADMIN_EMAILS；页面 frontend/admin.html）
业务层：ai.py（prompt → llm）、prompts.py（所有 prompt）、store/（存储）、transcription/（转录源）、
quota.py（免费配额）、usage.py（按用户记用量）。
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .routes import admin, ai, auth, lectures, transcribe

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(title="LecTrace")
app.include_router(auth.router)
app.include_router(lectures.router)
app.include_router(ai.router)
app.include_router(transcribe.router)
app.include_router(admin.router)


@app.get("/api/health")
def health() -> dict:
    s = get_settings()
    return {
        "status": "ok",
        "transcription_source": s.transcription_source,
        "store_backend": s.store_backend,
        "llm_provider": s.llm_provider,
        "llm_model": s.llm_model,
        "llm_configured": s.llm_configured,
    }


# 前端静态托管（放最后，避免盖住 /api 与 /ws 路由）
# no-cache ≠ 不缓存：浏览器每次用 ETag 回源校验，没变就 304，变了立刻拿新的。
# 否则改了 CSS/JS 后用户拿到新 HTML 配旧样式，界面会错乱。
_NO_CACHE = {"Cache-Control": "no-cache"}


class _FreshStaticFiles(StaticFiles):
    def file_response(self, *args, **kwargs):  # type: ignore[override]
        resp = super().file_response(*args, **kwargs)
        resp.headers.update(_NO_CACHE)
        return resp


if FRONTEND_DIR.exists():

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html", headers=_NO_CACHE)

    app.mount("/", _FreshStaticFiles(directory=FRONTEND_DIR), name="static")
