"""转录 WebSocket：/ws/transcribe?session=<id>。

来源（麦克风 / 回放）、讲义语言、归档文件都从讲义 meta 读；暂停后再连同一 session
即续接（seq 与时间轴 t 接着走）。协议（服务端 → 前端）：
  {"type": "session", session_id, source, resumed, t_offset, ...}
  {"type": "interim", text}             临时结果（麦克风）
  {"type": "segment", seq, text, t}     定稿段落
  {"type": "end"} / {"type": "error", message}
前端 → 服务端：二进制 PCM 帧（麦克风），或文本 "stop"（暂停）。
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..auth import ws_user
from ..config import get_settings
from ..deps import get_store
from ..models import Segment, SessionInfo
from ..transcription import ReplaySource, list_demo_sessions, make_stt_runner

log = logging.getLogger("lectrace.ws")
router = APIRouter()


@router.websocket("/ws/transcribe")
async def ws_transcribe(ws: WebSocket) -> None:
    await ws.accept()
    settings = get_settings()
    user = ws_user(ws, settings)
    if user is None:
        await ws.send_json({"type": "error", "message": "未登录。", "code": "unauthorized"})
        await ws.close(code=4401)
        return
    session_id = ws.query_params.get("session") or ""
    info = await get_store().get_session(session_id) if session_id else None
    if info is None or info.user_id != user.id:
        await ws.send_json({"type": "error", "message": "讲义不存在或无权访问。"})
        await ws.close(code=4404)
        return
    try:
        if info.source == "replay":
            await _run_replay(ws, info)
        else:
            await _run_stt(ws, info)
    except WebSocketDisconnect:
        return
    except Exception as exc:  # noqa: BLE001 - 兜底反馈给前端
        log.exception("transcribe failed")
        await _send(ws, {"type": "error", "message": str(exc)})
    await _send(ws, {"type": "end"})


async def _send(ws: WebSocket, data: dict) -> None:
    try:
        await ws.send_json(data)
    except Exception:  # 对端已关
        pass


async def _wait_stop(ws: WebSocket, on_audio=None) -> None:
    """消费客户端消息直到 stop / 断开；二进制帧交给 on_audio。"""
    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect" or msg.get("text") == "stop":
                return
            if on_audio and msg.get("bytes") is not None:
                await on_audio(msg["bytes"])
    except WebSocketDisconnect:
        return


# ---------------- 回放 ----------------
async def _run_replay(ws: WebSocket, info: SessionInfo) -> None:
    settings = get_settings()
    store = get_store()
    speed = float(ws.query_params.get("speed") or settings.replay_speed)
    available = list_demo_sessions(settings.demo_data_dir)
    file = info.file or (available[-1]["file"] if available else "")
    path = settings.demo_data_dir / file if file else None
    if path is None or not path.exists():
        await _send(ws, {"type": "error", "message": f"找不到归档文件: {file or '(无)'}"})
        return

    # 暂停后续播：跳过已经播过的段落（t <= 已有最大 t）
    t_offset = await store.latest_t(info.id) if info.segment_count > 0 else 0.0
    replay = ReplaySource(path, speed=speed, max_gap_sec=settings.replay_max_gap_sec, start_after_t=t_offset)
    await ws.send_json({
        "type": "session", "session_id": info.id, "source": "replay", "file": file,
        "total_segments": len(replay.segments), "speed": speed,
        "resumed": t_offset > 0, "t_offset": t_offset,
    })

    stopper = asyncio.create_task(_wait_stop(ws))
    try:
        async for seg in replay.stream():
            if stopper.done():  # 暂停 / 断开：停在当前位置，下次续播
                break
            await store.append(info.id, seg)
            await ws.send_json({"type": "segment", **seg.model_dump()})
    finally:
        stopper.cancel()


# ---------------- 麦克风实时 STT ----------------
STT_FLUSH_TIMEOUT = 15.0  # 停止后等 STT 把尾段 final 冲出来的时间


async def _run_stt(ws: WebSocket, info: SessionInfo) -> None:
    settings = get_settings()
    store = get_store()

    seq, t_offset = 0, 0.0
    if info.segment_count > 0:  # 续接：从已有段落末尾接着编号 / 计时
        segs = await store.all_segments(info.id)
        if segs:
            seq, t_offset = segs[-1].seq, segs[-1].t
    await ws.send_json({
        "type": "session", "session_id": info.id, "source": info.source,
        "lang": info.lecture_language, "resumed": seq > 0, "t_offset": t_offset,
    })

    loop = asyncio.get_event_loop()
    started = loop.time()
    audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    async def on_interim(text: str) -> None:
        await ws.send_json({"type": "interim", "text": text})

    async def on_final(text: str) -> None:
        nonlocal seq
        seq += 1
        seg = Segment(seq=seq, text=text, t=t_offset + (loop.time() - started))
        await store.append(info.id, seg)
        await ws.send_json({"type": "segment", **seg.model_dump()})

    async def receive() -> None:
        try:
            await _wait_stop(ws, on_audio=audio_queue.put)
        finally:
            await audio_queue.put(None)  # 通知 STT 结束

    runner = make_stt_runner(info.source, settings)
    recv_task = asyncio.create_task(receive())
    stt_task = asyncio.create_task(runner(audio_queue, info.lecture_language, on_interim, on_final))
    done, _ = await asyncio.wait({recv_task, stt_task}, return_when=asyncio.FIRST_COMPLETED)

    if stt_task in done:
        # STT 先结束多半是出错（缺凭证 / 权限等）
        recv_task.cancel()
        if (exc := stt_task.exception()) is not None:
            raise exc
        return
    # 收流结束（暂停 / 断开）：等 STT 把尾部 final 冲出来再结束，不要立即 cancel
    try:
        await asyncio.wait_for(stt_task, timeout=STT_FLUSH_TIMEOUT)
    except asyncio.TimeoutError:
        stt_task.cancel()
