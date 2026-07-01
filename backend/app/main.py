"""LecTrace 后端：WebSocket 转录流 + Catchup 摘要 + 前端静态托管。

demo 数据流：前端 —WS—> 后端(回放归档 session) —> 前端展示；
                前端 —POST /api/catchup—> 后端取最近 X 分钟 —> Gemini —> 摘要。
目标数据流：把回放源换成 GoogleSTTSource（前端上行音频 —> 后端代理 STT streaming）。
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .chat import ConversationStore, chat_stream
from .config import get_settings
from .gemini import GeminiError
from .models import CatchupRequest, ChatRequest, Segment
from .store import get_store
from .summarize import summarize_stream
from .transcription import ReplaySource, list_demo_sessions

settings = get_settings()
store = get_store()
conversations = ConversationStore()

# 对话上下文用的转录窗口（秒）
CHAT_CONTEXT_WINDOW_SEC = 1200.0
CHAT_CONTEXT_MAX_CHARS = 6000

app = FastAPI(title="LecTrace")

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "transcription_source": settings.transcription_source,
        "store_backend": settings.store_backend,
        "gemini_configured": settings.gemini_configured,
        "gemini_model": settings.gemini_model,
    }


@app.get("/api/sessions")
def sessions() -> dict:
    """可回放的归档 session 列表（demo 用）。"""
    return {"sessions": list_demo_sessions(settings.demo_data_dir)}


@app.websocket("/ws/transcribe")
async def ws_transcribe(ws: WebSocket) -> None:
    """建立会话并推送转录段落。

    query: file=<归档文件名>（可选，缺省用最新一个）、speed=<倍率>（可选）。
    """
    await ws.accept()

    file = ws.query_params.get("file")
    speed = float(ws.query_params.get("speed") or settings.replay_speed)

    available = list_demo_sessions(settings.demo_data_dir)
    if not available:
        await ws.send_json({"type": "error", "message": "没有可回放的归档 session。"})
        await ws.close()
        return
    if not file:
        file = available[-1]["file"]

    path = settings.demo_data_dir / file
    if not path.exists():
        await ws.send_json({"type": "error", "message": f"找不到 session 文件: {file}"})
        await ws.close()
        return

    session_id = uuid.uuid4().hex
    store.create_session(session_id, meta={"file": file})
    source = ReplaySource(path, speed=speed, max_gap_sec=settings.replay_max_gap_sec)

    await ws.send_json(
        {
            "type": "session",
            "session_id": session_id,
            "file": file,
            "total_segments": len(source.segments),
            "speed": speed,
        }
    )

    try:
        async for seg in source.stream():
            store.append(session_id, seg)
            await ws.send_json(
                {"type": "segment", "seq": seg.seq, "text": seg.text, "t": seg.t}
            )
        await ws.send_json({"type": "end"})
    except WebSocketDisconnect:
        return
    except Exception as exc:  # noqa: BLE001 - 兜底反馈给前端
        try:
            await ws.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass


def _sse(event: str | None, data: dict) -> str:
    prefix = f"event: {event}\n" if event else ""
    return f"{prefix}data: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/catchup")
async def catchup(req: CatchupRequest) -> StreamingResponse:
    """流式返回 Catchup 摘要（SSE）。

    事件：meta（时间窗/模型信息）→ 多个默认 message（{"text": 片段}）→ done / error。
    前置校验（会话/内容/key）在开流前完成，便于用普通 HTTP 状态码反馈。
    """
    now_t = store.latest_t(req.session_id)
    if now_t <= 0:
        raise HTTPException(status_code=404, detail="会话不存在或还没有转录内容。")

    start_t = max(0.0, now_t - req.window_minutes * 60.0)
    segs: list[Segment] = store.window(req.session_id, start_t, now_t)
    if not segs:
        raise HTTPException(status_code=404, detail="该时间窗内没有转录内容。")
    if not settings.gemini_configured:
        raise HTTPException(status_code=502, detail="GEMINI_API_KEY 未配置，无法生成摘要。")

    async def gen():
        yield _sse(
            "meta",
            {
                "window_minutes": req.window_minutes,
                "covered_from": start_t,
                "covered_to": now_t,
                "segment_count": len(segs),
                "model": settings.gemini_model,
                "lecture_language": req.lecture_language,
                "user_language": req.user_language,
            },
        )
        try:
            async for chunk in summarize_stream(
                segs,
                req.window_minutes,
                req.lecture_language,
                req.user_language,
                settings,
            ):
                yield _sse(None, {"text": chunk})
            yield _sse("done", {})
        except GeminiError as exc:
            yield _sse("error", {"message": str(exc)})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _chat_context(session_id: str) -> str:
    """取最近一段转录作为对话上下文。"""
    now_t = store.latest_t(session_id)
    if now_t <= 0:
        return ""
    start_t = max(0.0, now_t - CHAT_CONTEXT_WINDOW_SEC)
    segs = store.window(session_id, start_t, now_t)
    text = "\n".join(s.text for s in segs)
    return text[-CHAT_CONTEXT_MAX_CHARS:]


@app.get("/api/conversations")
def list_conversations(session_id: str) -> dict:
    convs = conversations.list(session_id)
    convs.sort(key=lambda c: c.created_t, reverse=True)
    return {"conversations": [c.summary() for c in convs]}


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str) -> dict:
    conv = conversations.get(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="对话不存在。")
    return {"id": conv.id, "title": conv.title, "messages": conv.messages}


@app.post("/api/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    """流式返回 AI 对话回复（SSE）。结合最近转录作为上下文，服务端保存多轮历史。"""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="消息为空。")
    if not settings.gemini_configured:
        raise HTTPException(status_code=502, detail="GEMINI_API_KEY 未配置，无法对话。")

    if req.conversation_id:
        conv = conversations.get(req.conversation_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="对话不存在。")
    else:
        title = req.message.strip()[:24]
        conv = conversations.create(req.session_id, title, store.latest_t(req.session_id))

    conv.messages.append({"role": "user", "content": req.message.strip()})
    history = list(conv.messages)
    context = _chat_context(req.session_id)

    async def gen():
        yield _sse("meta", {"conversation_id": conv.id, "title": conv.title})
        acc = ""
        try:
            async for chunk in chat_stream(history, context, req.user_language, settings):
                acc += chunk
                yield _sse(None, {"text": chunk})
            conv.messages.append({"role": "assistant", "content": acc})
            yield _sse("done", {})
        except GeminiError as exc:
            # 生成失败：回滚刚加入的用户消息，避免留下无回复的半截对话
            if conv.messages and conv.messages[-1]["role"] == "user":
                conv.messages.pop()
            yield _sse("error", {"message": str(exc)})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# 前端静态托管（放最后，避免盖住 /api 与 /ws 路由）
if FRONTEND_DIR.exists():

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")

    app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="static")
