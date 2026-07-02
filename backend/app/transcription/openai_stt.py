"""OpenAI Realtime API 实时转录代理（source=openai-stt）。

前端上行 24kHz / 16-bit / 单声道 PCM（二进制帧）→ 后端 base64 后经 Realtime WS
的 input_audio_buffer.append 送出 → 收 transcription.delta（增量）/ completed（整句）。

与 google_stt.run_stt 同签名，上层 _run_stt 可统一调度。
差异：OpenAI 的 delta 是增量片段，这里累加成累计文本再回调 on_interim，
      从而与 Google（累计 interim）对上层保持一致。
"""

from __future__ import annotations

import array
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
    silence_ms: int = 800,
    commit_ms: int = 4000,
) -> None:
    """从 audio_queue 取音频喂给 OpenAI Realtime，回调 interim / final。队列 None 结束。

    silence_ms：VAD 判定"说完一句"所需的静音时长。默认 VAD 阈值太短(~200ms)，
    讲师短停顿就切段 → 碎片太短 → 模型幻觉。调大到 ~800ms 合并短停顿，
    给模型足够上下文，转录更连贯。
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    audio_input = {
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
    session_update = {
        "type": "session.update",
        "session": {"type": "transcription", "audio": {"input": audio_input}},
    }

    async with connect(REALTIME_URL, additional_headers=headers, max_size=None) as ws:
        await ws.send(json.dumps(session_update))
        print(f"[stt] connected model={model} lang={lecture_lang}", flush=True)
        stopped = asyncio.Event()
        interim_buf = ""
        stats = {"bytes": 0, "chunks": 0, "delta": 0, "final": 0, "peak": 0}
        # whisper 无 VAD：需按固定时长定期 commit 才会定稿；transcribe 走 VAD 自动 commit
        needs_commit = "whisper" in model
        commit_every = int(SAMPLE_RATE * 2 * (commit_ms / 1000.0))  # 字节
        since_commit = 0

        async def sender() -> None:
            nonlocal since_commit
            while True:
                chunk = await audio_queue.get()
                if chunk is None:
                    try:
                        await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
                    except Exception:
                        pass
                    break
                stats["bytes"] += len(chunk)
                stats["chunks"] += 1
                # 采样峰值：接近 0 说明静音(采集问题)，几千+说明有声音
                try:
                    a = array.array("h")
                    a.frombytes(chunk)
                    if a:
                        p = max(abs(min(a)), abs(max(a)))
                        if p > stats["peak"]:
                            stats["peak"] = p
                except Exception:
                    pass
                await ws.send(
                    json.dumps(
                        {
                            "type": "input_audio_buffer.append",
                            "audio": base64.b64encode(chunk).decode(),
                        }
                    )
                )
                # whisper：每积累 commit_ms 就提交一次，得到定期的定稿段落
                if needs_commit:
                    since_commit += len(chunk)
                    if since_commit >= commit_every:
                        since_commit = 0
                        await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
            print(
                f"[stt] audio sent chunks={stats['chunks']} bytes={stats['bytes']} "
                f"peak={stats['peak']}/32767",
                flush=True,
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
                        stats["delta"] += 1
                        interim_buf += delta
                        await on_interim(interim_buf)
                elif tp.endswith("input_audio_transcription.completed"):
                    text = (e.get("transcript") or "").strip()
                    interim_buf = ""
                    if text:
                        stats["final"] += 1
                        await on_final(text)
                elif "error" in tp:
                    msg = (e.get("error") or {}).get("message", "OpenAI STT 错误")
                    print(f"[stt] ERROR event: {e.get('error')}", flush=True)
                    raise RuntimeError(msg)
                elif tp in ("session.created", "session.updated"):
                    print(f"[stt] {tp}", flush=True)

        send_task = asyncio.create_task(sender())
        read_task = asyncio.create_task(reader())
        await stopped.wait()
        # 停止后 commit 冲刷的尾段 final 可能要几秒才回来（缓冲越长越久），给足时间
        try:
            await asyncio.wait_for(asyncio.shield(read_task), timeout=10.0)
        except asyncio.TimeoutError:
            pass
        print(f"[stt] done delta={stats['delta']} final={stats['final']}", flush=True)
        for tk in (read_task, send_task):
            tk.cancel()
