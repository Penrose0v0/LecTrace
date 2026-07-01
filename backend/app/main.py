"""LecTrace 后端：WebSocket 转录流 + Catchup 摘要 + 前端静态托管。

demo 数据流：前端 —WS—> 后端(回放归档 session) —> 前端展示；
                前端 —POST /api/catchup—> 后端取最近 X 分钟 —> Gemini —> 摘要。
目标数据流：把回放源换成 GoogleSTTSource（前端上行音频 —> 后端代理 STT streaming）。
"""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .chat import chat_stream
from .config import get_settings
from .conversations import get_conversation_store
from .llm import LLMError
from .models import Card, CatchupRequest, ChatRequest, Segment
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


@app.get("/api/sessions")
def sessions() -> dict:
    """可回放的归档 session 列表（demo 用）。"""
    return {"sessions": list_demo_sessions(settings.demo_data_dir)}


@app.websocket("/ws/transcribe")
async def ws_transcribe(ws: WebSocket) -> None:
    """转录 WebSocket。source=replay（回放，服务端推）或 google-stt（前端上行音频）。"""
    await ws.accept()
    source = ws.query_params.get("source") or settings.transcription_source
    if source in ("google-stt", "openai-stt"):
        await _run_stt(ws, source)
    else:
        await _run_replay(ws)


async def _run_replay(ws: WebSocket) -> None:
    """回放归档 session：服务端按节奏推送转录（query: file, speed）。"""
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
    await store.create_session(session_id, meta={"source": "replay", "file": file})
    replay = ReplaySource(path, speed=speed, max_gap_sec=settings.replay_max_gap_sec)

    await ws.send_json(
        {
            "type": "session",
            "session_id": session_id,
            "source": "replay",
            "file": file,
            "total_segments": len(replay.segments),
            "speed": speed,
        }
    )

    try:
        async for seg in replay.stream():
            await store.append(session_id, seg)
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


async def _run_stt(ws: WebSocket, source: str) -> None:
    """前端上行麦克风音频（二进制 PCM 帧）→ 代理 STT（Google/OpenAI）→ 回推转录。

    source: google-stt（16k）或 openai-stt（24k）。query: lang=ja|en|zh（讲义语言）。
    t 用会话开始起的服务端时钟。
    """
    lang = ws.query_params.get("lang") or settings.lecture_language

    # 续接已有 session（resume）：seq 与时间轴 t 接着上次继续
    resume_id = ws.query_params.get("session")
    seq = 0
    t_offset = 0.0
    resumed = False
    if resume_id:
        segs = await store.all_segments(resume_id)
        if segs:
            seq = segs[-1].seq
            t_offset = segs[-1].t
            session_id = resume_id
            resumed = True
    if not resumed:
        session_id = uuid.uuid4().hex
        await store.create_session(session_id, meta={"source": source, "lang": lang})

    await ws.send_json(
        {
            "type": "session",
            "session_id": session_id,
            "source": source,
            "lang": lang,
            "resumed": resumed,
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
        )
    else:
        from .transcription.google_stt import run_stt

        runner = run_stt(audio_queue, lang, on_interim, on_final)

    recv_task = asyncio.create_task(receive_loop())
    stt_task = asyncio.create_task(runner)

    done, _ = await asyncio.wait(
        {recv_task, stt_task}, return_when=asyncio.FIRST_COMPLETED
    )

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
            await asyncio.wait_for(stt_task, timeout=10)
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


def _sse(event: str | None, data: dict) -> str:
    prefix = f"event: {event}\n" if event else ""
    return f"{prefix}data: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/catchup")
async def catchup(req: CatchupRequest) -> StreamingResponse:
    """流式返回 Catchup 摘要（SSE）。

    事件：meta（时间窗/模型信息）→ 多个默认 message（{"text": 片段}）→ done / error。
    前置校验（会话/内容/key）在开流前完成，便于用普通 HTTP 状态码反馈。
    """
    now_t = await store.latest_t(req.session_id)
    if now_t <= 0:
        raise HTTPException(status_code=404, detail="会话不存在或还没有转录内容。")

    start_t = max(0.0, now_t - req.window_minutes * 60.0)
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
        lecture_language=req.lecture_language,
        user_language=req.user_language,
        created_t=now_t,
    )

    async def gen():
        yield _sse(
            "meta",
            {
                "card_id": card.id,
                "index": card.index,
                "window_minutes": req.window_minutes,
                "covered_from": start_t,
                "covered_to": now_t,
                "segment_count": len(segs),
                "model": settings.llm_model,
                "lecture_language": req.lecture_language,
                "user_language": req.user_language,
            },
        )
        acc = ""
        try:
            async for chunk in summarize_stream(
                segs,
                req.window_minutes,
                req.lecture_language,
                req.user_language,
                settings,
            ):
                acc += chunk
                yield _sse(None, {"text": chunk})
            card.summary = acc
            await store.add_card(req.session_id, card)  # 摘要完成后持久化卡片
            yield _sse("done", {})
        except LLMError as exc:
            yield _sse("error", {"message": str(exc)})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/sessions/{session_id}/cards")
async def list_cards(session_id: str) -> dict:
    """该会话已生成的 Catchup 卡片（持久化后可用于重载）。"""
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


@app.get("/api/conversations")
async def list_conversations(session_id: str) -> dict:
    convs = await conversations.list(session_id)
    convs.sort(key=lambda c: c.created_t, reverse=True)
    return {"conversations": [c.summary() for c in convs]}


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str) -> dict:
    conv = await conversations.get(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="对话不存在。")
    return {"id": conv.id, "title": conv.title, "messages": conv.messages}


@app.post("/api/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    """流式返回 AI 对话回复（SSE）。结合最近转录作为上下文，服务端保存多轮历史。"""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="消息为空。")
    if not settings.llm_configured:
        raise HTTPException(status_code=502, detail="LLM 未配置 API key，无法对话。")

    if req.conversation_id:
        conv = await conversations.get(req.conversation_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="对话不存在。")
    else:
        title = req.message.strip()[:24]
        conv = await conversations.create(
            req.session_id, title, await store.latest_t(req.session_id)
        )

    conv.messages.append({"role": "user", "content": req.message.strip()})
    history = list(conv.messages)
    context = await _chat_context(req.session_id)

    async def gen():
        yield _sse("meta", {"conversation_id": conv.id, "title": conv.title})
        acc = ""
        try:
            async for chunk in chat_stream(history, context, req.user_language, settings):
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
