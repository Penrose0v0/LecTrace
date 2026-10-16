"""转录源：

- 实时 STT（麦克风）：openai-stt / google-stt（v1）/ google-stt-v2（Chirp 3），统一签名
  `run_stt(audio_queue, lecture_lang, on_interim, on_final)`，由 `make_stt_runner` 按配置绑好参数。
- 回放：ReplaySource 按原时间轴（加速）重放归档 session。
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Coroutine

from ..config import Settings
from .replay import ReplaySource, list_demo_sessions

OnText = Callable[[str], Awaitable[None]]
STTRunner = Callable[["asyncio.Queue[bytes | None]", str, OnText, OnText], Coroutine]


def stt_sample_rate(source: str) -> int:
    """前端按来源上行的 PCM 采样率（16-bit 单声道）。"""
    if source == "openai-stt":
        from .openai_stt import SAMPLE_RATE
    else:
        from .google_stt import SAMPLE_RATE
    return SAMPLE_RATE


def make_stt_runner(source: str, settings: Settings) -> STTRunner:
    if source == "openai-stt":
        from .openai_stt import run_stt as openai_run

        async def runner(q, lang, on_interim, on_final):
            await openai_run(
                q, lang, on_interim, on_final,
                api_key=settings.openai_api_key, model=settings.openai_stt_model,
                silence_ms=settings.openai_stt_silence_ms, commit_ms=settings.openai_stt_commit_ms,
                rotate_sec=settings.openai_stt_rotate_sec,
            )

        return runner
    if source == "google-stt":
        from .google_stt import run_stt as google_run

        return google_run
    if source == "google-stt-v2":
        from .google_stt_v2 import run_stt as google_v2_run

        async def runner_v2(q, lang, on_interim, on_final):
            await google_v2_run(
                q, lang, on_interim, on_final,
                project=settings.gcp_project,
                location=settings.google_stt_v2_location, model=settings.google_stt_v2_model,
            )

        return runner_v2
    raise ValueError(f"未知转录来源: {source}")


__all__ = ["ReplaySource", "list_demo_sessions", "make_stt_runner", "stt_sample_rate", "STTRunner", "OnText"]
