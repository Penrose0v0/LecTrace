"""OpenAI Realtime API 实时转录代理（source=openai-stt）。

前端上行 24kHz / 16-bit / 单声道 PCM（二进制帧）→ 后端 base64 后经 Realtime WS
的 input_audio_buffer.append 送出 → 收 transcription.delta（增量）/ completed（整句）。

与 google_stt.run_stt 同签名，上层 _run_stt 可统一调度。
差异：OpenAI 的 delta 是增量片段，这里累加成累计文本再回调 on_interim，
      从而与 Google（累计 interim）对上层保持一致。
"""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Awaitable, Callable

from websockets.asyncio.client import connect

# OpenAI 用 ISO-639-1 语言码
LANG_MAP = {"ja": "ja", "en": "en", "zh": "zh"}
SAMPLE_RATE = 24000
REALTIME_URL = "wss://api.openai.com/v1/realtime?intent=transcription"

OnText = Callable[[str], Awaitable[None]]


def lang_code(lecture_lang: str) -> str:
    return LANG_MAP.get(lecture_lang, "ja")


async def run_stt(
    audio_queue: "asyncio.Queue[bytes | None]",
    lecture_lang: str,
    on_interim: OnText,
    on_final: OnText,
    *,
    api_key: str,
    model: str,
) -> None:
    """从 audio_queue 取音频喂给 OpenAI Realtime，回调 interim / final。队列 None 结束。"""
    headers = {"Authorization": f"Bearer {api_key}"}
    session_update = {
        "type": "session.update",
        "session": {
            "type": "transcription",
            "audio": {
                "input": {
                    "format": {"type": "audio/pcm", "rate": SAMPLE_RATE},
                    "transcription": {"model": model, "language": lang_code(lecture_lang)},
                }
            },
        },
    }

    async with connect(REALTIME_URL, additional_headers=headers, max_size=None) as ws:
        await ws.send(json.dumps(session_update))
        stopped = asyncio.Event()
        interim_buf = ""

        async def sender() -> None:
            while True:
                chunk = await audio_queue.get()
                if chunk is None:
                    # 停止时强制提交缓冲，冲刷最后一段（否则尾句不 finalize）
                    try:
                        await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
                    except Exception:
                        pass
                    break
                await ws.send(
                    json.dumps(
                        {
                            "type": "input_audio_buffer.append",
                            "audio": base64.b64encode(chunk).decode(),
                        }
                    )
                )
            stopped.set()

        async def reader() -> None:
            nonlocal interim_buf
            async for raw in ws:
                e = json.loads(raw)
                tp = e.get("type", "")
                if tp.endswith("input_audio_transcription.delta"):
                    delta = e.get("delta", "")
                    if delta:
                        interim_buf += delta
                        await on_interim(interim_buf)
                elif tp.endswith("input_audio_transcription.completed"):
                    text = (e.get("transcript") or "").strip()
                    interim_buf = ""
                    if text:
                        await on_final(text)
                elif "error" in tp:
                    msg = (e.get("error") or {}).get("message", "OpenAI STT 错误")
                    raise RuntimeError(msg)

        send_task = asyncio.create_task(sender())
        read_task = asyncio.create_task(reader())
        await stopped.wait()
        # 停止后再给一小段时间收尾尾部 final
        try:
            await asyncio.wait_for(asyncio.shield(read_task), timeout=2.0)
        except asyncio.TimeoutError:
            pass
        for tk in (read_task, send_task):
            tk.cancel()
