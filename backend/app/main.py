"""LecTrace 后端：登录 + 讲义会话 + WebSocket 转录流 + Catchup / 对话 + 前端静态托管。

数据流：
  前端 —POST /api/sessions—> 建一节课（meta）
  前端 —WS /ws/transcribe?session=id—> 上行麦克风音频 → 代理 STT → 回推转录（或回放归档）
  前端 —POST /api/catchup—> 后端取最近 X 分钟 → LLM → 摘要（SSE），结果追加进对话线程
  前端 —POST /api/chat—> 结合最近转录的多轮对话（SSE）
所有 /api/sessions* /api/catchup /api/chat /ws 都要求登录，并校验讲义归属。
"""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .auth import (
    DEV_USER,
    User,
    clear_session_cookie,
    current_user,
    optional_user,
    set_session_cookie,
    verify_google_credential,
    ws_user,
)
from .chat import chat_stream, preset_message
from .config import get_settings
from .conversations import get_conversation_store
from .llm import LLMError
from .models import (
    LANGS,
    SOURCES,
    Card,
    CatchupRequest,
    ChatRequest,
    GoogleLoginRequest,
    LectureMeta,
    LectureUpdate,
    Segment,
    SessionInfo,
    UserPrefs,
)
from .store import get_store
from .summarize import summarize_stream
from .transcription import ReplaySource, list_demo_sessions

settings = get_settings()
store = get_store()
conversations = get_conversation_store()

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
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "llm_configured": settings.llm_configured,
    }


# =====================================================================
# 登录
# =====================================================================
@app.get("/api/auth/config")
def auth_config() -> dict:
    """前端据此决定渲染 Google 按钮还是本地开发登录。"""
    return {"google_client_id": settings.google_client_id, "dev_login": settings.auth_dev_login}


@app.post("/api/auth/google")
async def auth_google(req: GoogleLoginRequest, request: Request, response: Response) -> dict:
    user = await verify_google_credential(req.credential, settings)
    set_session_cookie(response, request, user, settings)
    return {"user": user.model_dump(), "prefs": await _prefs(user)}


@app.post("/api/auth/dev")
async def auth_dev(request: Request, response: Response) -> dict:
    if not settings.auth_dev_login:
        raise HTTPException(status_code=403, detail="本地开发登录未开启。")
    set_session_cookie(response, request, DEV_USER, settings)
    return {"user": DEV_USER.model_dump(), "prefs": await _prefs(DEV_USER)}


@app.post("/api/auth/logout")
def auth_logout(response: Response) -> dict:
    clear_session_cookie(response)
    return {"ok": True}


@app.get("/api/auth/me")
async def auth_me(user: User | None = Depends(optional_user)) -> dict:
    if user is None:
        return {"user": None}
    return {"user": user.model_dump(), "prefs": await _prefs(user)}


async def _prefs(user: User) -> dict:
    prefs = await store.get_prefs(user.id)
    return (prefs or UserPrefs()).model_dump()


@app.put("/api/me/prefs")
async def save_prefs(prefs: UserPrefs, user: User = Depends(current_user)) -> dict:
    if prefs.ui_language not in LANGS or prefs.lecture_language not in LANGS:
        raise HTTPException(status_code=400, detail="不支持的语言。")
    await store.save_prefs(user.id, prefs)
    return prefs.model_dump()


# =====================================================================
# 讲义（session）
# =====================================================================
@app.get("/api/demo-sessions")
def demo_sessions(_: User = Depends(current_user)) -> dict:
    """可回放的归档 session 列表（demo / 本地测试用）。"""
    return {"sessions": list_demo_sessions(settings.demo_data_dir)}


def _validate_meta(meta: LectureMeta | LectureUpdate) -> None:
    if meta.lecture_language is not None and meta.lecture_language not in LANGS:
        raise HTTPException(status_code=400, detail="不支持的讲义语言。")
    if meta.user_language is not None and meta.user_language not in LANGS:
        raise HTTPException(status_code=400, detail="不支持的用户语言。")
    if meta.source is not None and meta.source not in SOURCES:
        raise HTTPException(status_code=400, detail="不支持的转录来源。")


@app.post("/api/sessions")
async def create_session(meta: LectureMeta, user: User = Depends(current_user)) -> dict:
    _validate_meta(meta)
    session_id = uuid.uuid4().hex
    await store.create_session(session_id, meta={"user_id": user.id, **meta.model_dump()})
    info = await store.get_session(session_id)
    return info.model_dump() if info else {"id": session_id}


@app.get("/api/sessions")
async def list_sessions(user: User = Depends(current_user)) -> dict:
    return {"sessions": [s.model_dump() for s in await store.list_sessions(user.id)]}


async def _owned(session_id: str, user: User) -> SessionInfo:
    info = await store.get_session(session_id)
    if info is None:
        raise HTTPException(status_code=404, detail="讲义不存在。")
    if info.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权访问这节课。")
    return info


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str, user: User = Depends(current_user)) -> dict:
    """讲义详情 + 全部转录（回看 / resume 用）。"""
    info = await _owned(session_id, user)
    segs = await store.all_segments(session_id)
    return {"session": info.model_dump(), "segments": [s.model_dump() for s in segs]}


@app.patch("/api/sessions/{session_id}")
async def update_session(
    session_id: str, patch: LectureUpdate, user: User = Depends(current_user)
) -> dict:
    await _owned(session_id, user)
    _validate_meta(patch)
    data = patch.model_dump(exclude_none=True)
    if data:
        await store.update_session(session_id, data)
    info = await store.get_session(session_id)
    return info.model_dump() if info else {}


# =====================================================================
# 转录 WebSocket
# =====================================================================
@app.websocket("/ws/transcribe")
async def ws_transcribe(ws: WebSocket) -> None:
    """转录 WebSocket：?session=<id>。来源（麦克风 / 回放）由讲义 meta 决定。"""
    await ws.accept()
    user = ws_user(ws, settings)
    if user is None:
        await ws.send_json({"type": "error", "message": "未登录。", "code": "unauthorized"})
        await ws.close(code=4401)
        return
    session_id = ws.query_params.get("session") or ""
    info = await store.get_session(session_id) if session_id else None
    if info is None or info.user_id != user.id:
        await ws.send_json({"type": "error", "message": "讲义不存在或无权访问。"})
        await ws.close(code=4404)
        return
    if info.source == "replay":
        await _run_replay(ws, info)
    else:
        await _run_stt(ws, info)


async def _run_replay(ws: WebSocket, info: SessionInfo) -> None:
    """回放归档 session：服务端按节奏推送转录（讲义 meta 里的 file；query speed 可覆盖）。"""
    speed = float(ws.query_params.get("speed") or settings.replay_speed)
    available = list_demo_sessions(settings.demo_data_dir)
    file = info.file or (available[-1]["file"] if available else "")
    path = settings.demo_data_dir / file if file else None
    if path is None or not path.exists():
        await ws.send_json({"type": "error", "message": f"找不到归档文件: {file or '(无)'}"})
        await ws.close()
        return
    # 暂停后续播：跳过已经播过的段落（t <= 已有最大 t），从那之后接着推
    t_offset = await store.latest_t(info.id) if info.segment_count > 0 else 0.0
    replay = ReplaySource(
        path, speed=speed, max_gap_sec=settings.replay_max_gap_sec, start_after_t=t_offset
    )
    await ws.send_json(
        {
            "type": "session",
            "session_id": info.id,
            "source": "replay",
            "file": file,
            "total_segments": len(replay.segments),
            "speed": speed,
            "resumed": t_offset > 0,
            "t_offset": t_offset,
        }
    )

    async def watch_close() -> None:
        # 客户端主动断开 / 发 stop 时结束回放
        try:
            while True:
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect" or msg.get("text") == "stop":
                    return
        except WebSocketDisconnect:
            return

    watcher = asyncio.create_task(watch_close())
    try:
        async for seg in replay.stream():
            if watcher.done():  # 客户端暂停（stop）/ 断开：停在当前位置，下次续播
                break
            await store.append(info.id, seg)
            await ws.send_json({"type": "segment", "seq": seg.seq, "text": seg.text, "t": seg.t})
    except WebSocketDisconnect:
        return
    except Exception as exc:  # noqa: BLE001 - 兜底反馈给前端
        try:
            await ws.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        watcher.cancel()
    try:
        await ws.send_json({"type": "end"})
    except Exception:
        pass


async def _run_stt(ws: WebSocket, info: SessionInfo) -> None:
    """前端上行麦克风音频（二进制 PCM 帧）→ 代理 STT（Google/OpenAI）→ 回推转录。

    source: google-stt（16k）或 openai-stt（24k）；讲义语言来自会话 meta。
    t 用会话开始起的服务端时钟；续接时从已有段落的末尾 seq / t 接着走。
    """
    source = info.source
    lang = info.lecture_language
    session_id = info.id

    seq = 0
    t_offset = 0.0
    resumed = False
    if info.segment_count > 0:
        segs = await store.all_segments(session_id)
        if segs:
            seq = segs[-1].seq
            t_offset = segs[-1].t
            resumed = True

    await ws.send_json(
        {
            "type": "session",
            "session_id": session_id,
            "source": source,
            "lang": lang,
            "resumed": resumed,
            "t_offset": t_offset,
        }
    )

    loop = asyncio.get_event_loop()
    session_start = loop.time()
    audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    async def on_interim(text: str) -> None:
        await ws.send_json({"type": "interim", "text": text})

    async def on_final(text: str) -> None:
        nonlocal seq
        seq += 1
        t = t_offset + (loop.time() - session_start)
        seg = Segment(seq=seq, text=text, t=t)
        await store.append(session_id, seg)
        await ws.send_json({"type": "segment", "seq": seq, "text": text, "t": t})

    async def receive_loop() -> None:
        try:
            while True:
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect":
                    break
                if msg.get("bytes") is not None:
                    await audio_queue.put(msg["bytes"])
                elif msg.get("text") == "stop":
                    break
        except WebSocketDisconnect:
            pass
        finally:
            await audio_queue.put(None)  # 通知 STT 结束

    if source == "openai-stt":
        from .transcription.openai_stt import run_stt

        runner = run_stt(
            audio_queue, lang, on_interim, on_final,
            api_key=settings.openai_api_key, model=settings.openai_stt_model,
            silence_ms=settings.openai_stt_silence_ms,
            commit_ms=settings.openai_stt_commit_ms,
        )
    else:
        from .transcription.google_stt import run_stt

        runner = run_stt(audio_queue, lang, on_interim, on_final)

    recv_task = asyncio.create_task(receive_loop())
    stt_task = asyncio.create_task(runner)

    done, _ = await asyncio.wait({recv_task, stt_task}, return_when=asyncio.FIRST_COMPLETED)

    if stt_task in done:
        # STT 先结束多半是出错（缺凭证/权限等）
        exc = stt_task.exception()
        if exc is not None:
            try:
                await ws.send_json({"type": "error", "message": str(exc)})
            except Exception:
                pass
        recv_task.cancel()
    else:
        # 收流结束（stop/断开）：通知 STT 收尾，并等它把尾部 final 冲出来后再结束，
        # 不要立即 cancel，否则最后一段 final 会丢。
        await audio_queue.put(None)
        try:
            await asyncio.wait_for(stt_task, timeout=15)
        except asyncio.TimeoutError:
            stt_task.cancel()
        except Exception as exc:  # noqa: BLE001
            try:
                await ws.send_json({"type": "error", "message": str(exc)})
            except Exception:
                pass

    try:
        await ws.send_json({"type": "end"})
    except Exception:
        pass


# =====================================================================
# Catchup / 对话
# =====================================================================
def _sse(event: str | None, data: dict) -> str:
    prefix = f"event: {event}\n" if event else ""
    return f"{prefix}data: {json.dumps(data, ensure_ascii=False)}\n\n"


_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


async def _thread_for(session_id: str, conversation_id: str | None, title: str, created_t: float):
    """取/建这节课的对话线程（Catch-up 结果和聊天都挂在线程上）。"""
    if conversation_id:
        conv = await conversations.get(conversation_id)
        if conv is not None and conv.session_id == session_id:
            return conv
    return await conversations.create(session_id, title, created_t)


@app.post("/api/catchup")
async def catchup(req: CatchupRequest, user: User = Depends(current_user)) -> StreamingResponse:
    """流式返回 Catchup 摘要（SSE），并把结果追加到对话线程里。

    事件：meta（时间窗/模型/线程信息）→ 多个默认 message（{"text": 片段}）→ done / error。
    前置校验（会话/内容/key）在开流前完成，便于用普通 HTTP 状态码反馈。
    """
    info = await _owned(req.session_id, user)
    window_minutes = float(req.window_minutes or info.window_minutes or 5.0)
    now_t = await store.latest_t(req.session_id)
    if now_t <= 0:
        raise HTTPException(status_code=404, detail="还没有转录内容。")

    start_t = max(0.0, now_t - window_minutes * 60.0)
    segs: list[Segment] = await store.window(req.session_id, start_t, now_t)
    if not segs:
        raise HTTPException(status_code=404, detail="该时间窗内没有转录内容。")
    if not settings.llm_configured:
        raise HTTPException(status_code=502, detail="LLM 未配置 API key，无法生成摘要。")

    index = await store.card_count(req.session_id) + 1
    card = Card(
        id=uuid.uuid4().hex,
        index=index,
        covered_from=start_t,
        covered_to=now_t,
        segment_count=len(segs),
        model=settings.llm_model,
        lecture_language=info.lecture_language,
        user_language=info.user_language,
        created_t=now_t,
    )
    conv = await _thread_for(req.session_id, req.conversation_id, f"Catch-up #{index}", now_t)

    async def gen():
        yield _sse(
            "meta",
            {
                "card_id": card.id,
                "index": card.index,
                "window_minutes": window_minutes,
                "covered_from": start_t,
                "covered_to": now_t,
                "segment_count": len(segs),
                "model": settings.llm_model,
                "conversation_id": conv.id,
                "conversation_title": conv.title,
            },
        )
        acc = ""
        try:
            async for chunk in summarize_stream(
                segs, window_minutes, info.lecture_language, info.user_language, settings
            ):
                acc += chunk
                yield _sse(None, {"text": chunk})
            card.summary = acc
            await store.add_card(req.session_id, card)  # 摘要完成后持久化卡片
            conv.messages.append(
                {
                    "role": "assistant",
                    "kind": "catchup",
                    "content": acc,
                    "card_id": card.id,
                    "index": card.index,
                    "covered_from": start_t,
                    "covered_to": now_t,
                    "segment_count": len(segs),
                }
            )
            await conversations.save(conv)
            yield _sse("done", {})
        except LLMError as exc:
            yield _sse("error", {"message": str(exc)})

    return StreamingResponse(gen(), media_type="text/event-stream", headers=_SSE_HEADERS)


@app.get("/api/sessions/{session_id}/cards")
async def list_cards(session_id: str, user: User = Depends(current_user)) -> dict:
    """该会话已生成的 Catchup 卡片。"""
    await _owned(session_id, user)
    cards = await store.list_cards(session_id)
    return {"cards": [c.model_dump() for c in cards]}


async def _chat_context(session_id: str) -> str:
    """取最近一段转录作为对话上下文。"""
    now_t = await store.latest_t(session_id)
    if now_t <= 0:
        return ""
    start_t = max(0.0, now_t - CHAT_CONTEXT_WINDOW_SEC)
    segs = await store.window(session_id, start_t, now_t)
    text = "\n".join(s.text for s in segs)
    return text[-CHAT_CONTEXT_MAX_CHARS:]


@app.get("/api/sessions/{session_id}/conversations")
async def list_conversations(session_id: str, user: User = Depends(current_user)) -> dict:
    await _owned(session_id, user)
    convs = await conversations.list(session_id)
    convs.sort(key=lambda c: c.created_t, reverse=True)
    return {"conversations": [c.summary() for c in convs]}


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, user: User = Depends(current_user)) -> dict:
    conv = await conversations.get(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="对话不存在。")
    await _owned(conv.session_id, user)
    return {"id": conv.id, "title": conv.title, "session_id": conv.session_id, "messages": conv.messages}


@app.post("/api/chat")
async def chat(req: ChatRequest, user: User = Depends(current_user)) -> StreamingResponse:
    """流式返回 AI 对话回复（SSE）。结合最近转录作为上下文，服务端保存多轮历史。

    preset=explain 等快捷指令：服务端按讲义的用户语言生成用户消息。
    """
    info = await _owned(req.session_id, user)
    message = req.message.strip()
    if req.preset:
        message = preset_message(req.preset, info.user_language) or ""
        if not message:
            raise HTTPException(status_code=400, detail="未知的快捷指令。")
    if not message:
        raise HTTPException(status_code=400, detail="消息为空。")
    if not settings.llm_configured:
        raise HTTPException(status_code=502, detail="LLM 未配置 API key，无法对话。")

    conv = await _thread_for(
        req.session_id, req.conversation_id, message[:24], await store.latest_t(req.session_id)
    )
    conv.messages.append({"role": "user", "content": message})
    history = list(conv.messages)
    context = await _chat_context(req.session_id)

    async def gen():
        yield _sse(
            "meta", {"conversation_id": conv.id, "title": conv.title, "user_message": message}
        )
        acc = ""
        try:
            async for chunk in chat_stream(history, context, info.user_language, settings):
                acc += chunk
                yield _sse(None, {"text": chunk})
            conv.messages.append({"role": "assistant", "content": acc})
            await conversations.save(conv)  # 成功后整体持久化（含新一轮问答）
            yield _sse("done", {})
        except LLMError as exc:
            # 失败不持久化；回滚内存对象里刚加入的用户消息，保持一致
            if conv.messages and conv.messages[-1]["role"] == "user":
                conv.messages.pop()
            yield _sse("error", {"message": str(exc)})

    return StreamingResponse(gen(), media_type="text/event-stream", headers=_SSE_HEADERS)


# 前端静态托管（放最后，避免盖住 /api 与 /ws 路由）
if FRONTEND_DIR.exists():

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")

    app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="static")
