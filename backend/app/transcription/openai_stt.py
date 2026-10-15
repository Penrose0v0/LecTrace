"""OpenAI Realtime API 实时转录代理（source=openai-stt）。

前端上行 24kHz / 16-bit / 单声道 PCM（二进制帧）→ 后端 base64 后经 Realtime WS
的 input_audio_buffer.append 送出 → 收 transcription.delta（增量）/ completed（整句）。

与 google_stt.run_stt 同签名，上层 _run_stt 可统一调度。
差异：OpenAI 的 delta 是增量片段，这里累加成累计文本再回调 on_interim，
      从而与 Google（累计 interim）对上层保持一致。

OpenAI 单个 Realtime 会话最长 60 分钟。这里在 SESSION_ROTATE_SEC 处主动换一条新会话，
上游意外断开也会自动重连接着转；音频一直在队列里，不会丢。只有收到 None（用户停止）才真正结束。
"""

from __future__ import annotations

import array
import asyncio
import base64
import json
import logging
from typing import Awaitable, Callable

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

log = logging.getLogger("lectrace.stt")

# OpenAI 用 ISO-639-1 语言码
LANG_MAP = {"ja": "ja", "en": "en", "zh": "zh"}
SAMPLE_RATE = 24000
REALTIME_URL = "wss://api.openai.com/v1/realtime?intent=transcription"
SESSION_ROTATE_SEC = 50 * 60  # 60 分钟硬上限前主动换会话
FLUSH_SEC = 10.0  # 停止 / 轮换时等尾段 final 的时间
RECONNECT_DELAY_SEC = 1.0

OnText = Callable[[str], Awaitable[None]]


def lang_code(lecture_lang: str) -> str:
    return LANG_MAP.get(lecture_lang, "ja")


def _peak(chunk: bytes) -> int:
    """采样峰值：接近 0 说明静音(采集问题)，几千+说明有声音。"""
    try:
        a = array.array("h")
        a.frombytes(chunk)
        return max(abs(min(a)), abs(max(a))) if a else 0
    except Exception:  # noqa: BLE001
        return 0


async def run_stt(
    audio_queue: "asyncio.Queue[bytes | None]",
    lecture_lang: str,
    on_interim: OnText,
    on_final: OnText,
    *,
    api_key: str,
    model: str,
    silence_ms: int = 800,
    commit_ms: int = 4000,
    rotate_sec: float = SESSION_ROTATE_SEC,
) -> None:
    """从 audio_queue 取音频喂给 OpenAI Realtime，回调 interim / final。队列 None 结束。

    silence_ms：VAD 判定"说完一句"所需的静音时长（只对 transcribe 系列模型生效）。
    commit_ms：whisper 没有 VAD，每积累这么久提交一次才会定稿。
    """
    session_update = _session_update(model, lecture_lang, silence_ms)
    attempt = 0
    while True:
        try:
            finished = await _one_session(
                audio_queue, session_update, model, on_interim, on_final,
                commit_ms=commit_ms, api_key=api_key, rotate_sec=rotate_sec,
            )
        except ConnectionClosed as exc:
            finished = False
            log.warning("[stt] upstream closed (%s); reconnecting", exc)
        if finished:
            return
        attempt += 1
        await asyncio.sleep(RECONNECT_DELAY_SEC)
        log.info("[stt] opening new upstream session (#%d)", attempt + 1)


def _session_update(model: str, lecture_lang: str, silence_ms: int) -> dict:
    audio_input: dict = {
        "format": {"type": "audio/pcm", "rate": SAMPLE_RATE},
        "transcription": {"model": model, "language": lang_code(lecture_lang)},
    }
    # 非流式的 transcribe 模型需要调大 VAD 静音阈值以免碎片；
    # gpt-realtime-whisper 是原生流式，不支持（也不需要）turn_detection。
    if "whisper" not in model:
        audio_input["turn_detection"] = {
            "type": "server_vad",
            "silence_duration_ms": silence_ms,
            "threshold": 0.5,
            "prefix_padding_ms": 300,
        }
    return {"type": "session.update", "session": {"type": "transcription", "audio": {"input": audio_input}}}


async def _one_session(
    audio_queue: "asyncio.Queue[bytes | None]",
    session_update: dict,
    model: str,
    on_interim: OnText,
    on_final: OnText,
    *,
    commit_ms: int,
    api_key: str,
    rotate_sec: float,
) -> bool:
    """跑一条上游会话。返回 True = 用户停止（整体结束）；False = 该换一条新会话继续。"""
    headers = {"Authorization": f"Bearer {api_key}"}
    async with connect(REALTIME_URL, additional_headers=headers, max_size=None) as ws:
        await ws.send(json.dumps(session_update))
        log.info("[stt] connected model=%s", model)
        stopped = asyncio.Event()  # 用户停止（队列收到 None）
        flushed = asyncio.Event()  # 最近一次 commit 的 final 已回来
        stats = {"bytes": 0, "chunks": 0, "delta": 0, "final": 0, "peak": 0}
        # whisper 无 VAD：需按固定时长定期 commit 才会定稿；transcribe 走 VAD 自动 commit
        needs_commit = "whisper" in model
        commit_every = int(SAMPLE_RATE * 2 * (commit_ms / 1000.0))  # 字节
        interim_buf = ""

        async def commit() -> None:
            await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))

        async def sender() -> None:
            since_commit = 0
            while True:
                chunk = await audio_queue.get()
                if chunk is None:
                    flushed.clear()
                    try:
                        await commit()
                    except ConnectionClosed:
                        pass
                    stopped.set()
                    return
                stats["bytes"] += len(chunk)
                stats["chunks"] += 1
                stats["peak"] = max(stats["peak"], _peak(chunk))
                await ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": base64.b64encode(chunk).decode()}))
                if needs_commit:
                    since_commit += len(chunk)
                    if since_commit >= commit_every:
                        since_commit = 0
                        await commit()

        async def reader() -> None:
            nonlocal interim_buf
            async for raw in ws:
                e = json.loads(raw)
                tp = e.get("type", "")
                if tp.endswith("input_audio_transcription.delta"):
                    delta = e.get("delta", "")
                    if delta:
                        stats["delta"] += 1
                        interim_buf += delta
                        await on_interim(interim_buf)
                elif tp.endswith("input_audio_transcription.completed"):
                    text = (e.get("transcript") or "").strip()
                    interim_buf = ""
                    if text:
                        stats["final"] += 1
                        await on_final(text)
                    flushed.set()
                elif "error" in tp:
                    err = e.get("error") or {}
                    if err.get("code") == "input_audio_buffer_commit_empty":
                        flushed.set()  # 停止 / 轮换时缓冲恰好为空，没东西可定稿，不算错
                        continue
                    log.error("[stt] error event: %s", err)
                    raise RuntimeError(err.get("message", "OpenAI STT 错误"))
                elif tp in ("session.created", "session.updated"):
                    log.info("[stt] %s", tp)

        send_task = asyncio.create_task(sender())
        read_task = asyncio.create_task(reader())
        stop_task = asyncio.create_task(stopped.wait())
        rotate_task = asyncio.create_task(asyncio.sleep(rotate_sec))
        try:
            done, _ = await asyncio.wait(
                {send_task, read_task, stop_task, rotate_task}, return_when=asyncio.FIRST_COMPLETED
            )
            if read_task in done:
                # 上游先结束：error 事件 → 抛出给上层；正常关闭 → 换新会话
                exc = read_task.exception()
                if exc is not None and not isinstance(exc, ConnectionClosed):
                    raise exc
                log.warning("[stt] upstream ended mid-session; will reconnect")
                return False
            if send_task in done and not stopped.is_set():
                # 发送失败（多半是上游关了）→ 换新会话
                exc = send_task.exception()
                log.warning("[stt] sender stopped: %s; will reconnect", exc)
                return False
            finished = stopped.is_set()
            if not finished:
                # 主动轮换：先 commit 把手里的音频定稿
                log.info("[stt] rotating upstream session before the 60-min limit")
                flushed.clear()
                try:
                    await commit()
                except ConnectionClosed:
                    pass
            # 等这次 commit 的 final 回来（缓冲越长越久），有上限
            try:
                await asyncio.wait_for(flushed.wait(), timeout=FLUSH_SEC)
            except asyncio.TimeoutError:
                log.warning("[stt] final did not arrive within %.0fs", FLUSH_SEC)
            return finished
        finally:
            log.info(
                "[stt] session done chunks=%d bytes=%d peak=%d/32767 delta=%d final=%d",
                stats["chunks"], stats["bytes"], stats["peak"], stats["delta"], stats["final"],
            )
            for tk in (send_task, read_task, stop_task, rotate_task):
                tk.cancel()
