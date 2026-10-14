"""LecTrace 后端入口：装配路由 + 前端静态托管。

路由分布：
  routes/auth.py        登录 / 登出 / 当前用户 / 偏好
  routes/lectures.py    讲义（session）增查改、归档列表、卡片与线程列表
  routes/ai.py          Catch-up 摘要、对话（SSE）
  routes/transcribe.py  转录 WebSocket（麦克风代理 STT / 回放）
业务层：ai.py（prompt → llm）、prompts.py（所有 prompt）、store/（存储）、transcription/（转录源）。
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .routes import ai, auth, lectures, transcribe

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(title="LecTrace")
app.include_router(auth.router)
app.include_router(lectures.router)
app.include_router(ai.router)
app.include_router(transcribe.router)


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
if FRONTEND_DIR.exists():

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")

    app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="static")
