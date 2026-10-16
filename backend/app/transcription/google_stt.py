"""Google Cloud Speech-to-Text 流式代理。

前端把麦克风音频（16kHz / 16-bit / 单声道 LINEAR16 PCM）经 WebSocket 二进制帧上行，
后端把音频喂给 STT streaming API，产出 interim（临时）/ final（最终）识别结果。

STT 单条流约有 5 分钟上限，这里在 ~4 分钟处自动重启新流，音频持续入队不丢，
从而支持整节课时长。凭证走 ADC（本地）/ 运行时服务账号（Cloud Run）。

STT 偶尔会在流中途报错（实测见过 INVALID_ARGUMENT "Request contains an invalid argument."，
音频本身正常、几分钟后又好了，像是服务端瞬时问题）。这种错误不往上抛，而是丢掉积压的音频、
稍等后开一条新流继续；连续失败超过 STREAM_MAX_RETRIES 次才真正报错。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from google.api_core import exceptions as gexc
from google.cloud import speech_v1 as speech

log = logging.getLogger("lectrace.stt")

# 讲义语言 -> STT BCP-47 语言码
LANG_MAP = {"ja": "ja-JP", "en": "en-US", "zh": "cmn-Hans-CN"}

SAMPLE_RATE = 16000
STREAM_RESTART_SEC = 240.0  # 在 5 分钟硬上限前重启
# 流中途出错后的重试：连续失败次数上限 + 每次重开前等待（秒）
STREAM_MAX_RETRIES = 4
STREAM_RETRY_DELAYS = (0.5, 1.0, 2.0, 4.0)
# 一条流活过这么久（秒）就认为服务是好的，连续失败计数清零
STREAM_HEALTHY_SEC = 20.0

OnText = Callable[[str], Awaitable[None]]


def lang_code(lecture_lang: str) -> str:
    return LANG_MAP.get(lecture_lang, "ja-JP")


def _drain(q: "asyncio.Queue[bytes | None]") -> bool:
    """丢掉队列里积压的音频（重开流前用，避免一口气灌进去）。遇到结束标记返回 True。"""
    while True:
        try:
            item = q.get_nowait()
        except asyncio.QueueEmpty:
            return False
        if item is None:
            return True


async def run_stt(
    audio_queue: "asyncio.Queue[bytes | None]",
    lecture_lang: str,
    on_interim: OnText,
    on_final: OnText,
) -> None:
    """从 audio_queue 取音频喂给 STT，回调 interim / final 文本。

    队列收到 None 视为结束。会在 STREAM_RESTART_SEC 处自动重启流；流出错时按上面的策略重试。
    """
    try:
        client = speech.SpeechAsyncClient()
    except Exception as exc:  # noqa: BLE001 - 本地多半是没配 ADC
        raise RuntimeError(
            "Google STT 需要 GCP 凭证：本地请先 `gcloud auth application-default login`，"
            "或在课堂设置里把音频来源改成 OpenAI。"
        ) from exc
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=SAMPLE_RATE,
        language_code=lang_code(lecture_lang),
        enable_automatic_punctuation=True,
    )
    streaming_config = speech.StreamingRecognitionConfig(
        config=config, interim_results=True
    )
    loop = asyncio.get_event_loop()
    stopped = False
    failures = 0  # 连续失败次数
    stream_no = 0

    while not stopped:
        stream_no += 1
        start = loop.time()
        stats = {"chunks": 0, "bytes": 0, "last": 0, "results": 0}

        async def requests():
            nonlocal stopped
            yield speech.StreamingRecognizeRequest(streaming_config=streaming_config)
            while loop.time() - start < STREAM_RESTART_SEC:
                chunk = await audio_queue.get()
                if chunk is None:
                    stopped = True
                    return
                if not chunk:  # 空帧不发，服务端会当成非法请求
                    continue
                stats["chunks"] += 1
                stats["bytes"] += len(chunk)
                stats["last"] = len(chunk)
                yield speech.StreamingRecognizeRequest(audio_content=chunk)

        try:
            responses = await client.streaming_recognize(requests=requests())
            async for response in responses:
                for result in response.results:
                    if not result.alternatives:
                        continue
                    text = result.alternatives[0].transcript.strip()
                    if not text:
                        continue
                    stats["results"] += 1
                    if result.is_final:
                        await on_final(text)
                    else:
                        await on_interim(text)
        except gexc.GoogleAPICallError as exc:
            age = loop.time() - start
            if age >= STREAM_HEALTHY_SEC:
                failures = 0
            failures += 1
            log.warning(
                "stt stream #%d failed after %.1fs (chunks=%d bytes=%d last=%d results=%d): %s %s"
                " — retry %d/%d",
                stream_no, age, stats["chunks"], stats["bytes"], stats["last"], stats["results"],
                type(exc).__name__, exc.message, failures, STREAM_MAX_RETRIES,
            )
            if stopped:  # 用户已暂停，尾段丢了就丢了，不弹错误
                return
            if failures > STREAM_MAX_RETRIES:
                raise
            await asyncio.sleep(STREAM_RETRY_DELAYS[min(failures, len(STREAM_RETRY_DELAYS)) - 1])
            if _drain(audio_queue):
                stopped = True
            continue
        if loop.time() - start >= STREAM_HEALTHY_SEC:
            failures = 0
