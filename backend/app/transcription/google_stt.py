"""Google Cloud Speech-to-Text 流式代理。

前端把麦克风音频（16kHz / 16-bit / 单声道 LINEAR16 PCM）经 WebSocket 二进制帧上行，
后端把音频喂给 STT streaming API，产出 interim（临时）/ final（最终）识别结果。

STT 单条流约有 5 分钟上限，这里在 ~4 分钟处自动重启新流，音频持续入队不丢，
从而支持整节课时长。凭证走 ADC（本地）/ 运行时服务账号（Cloud Run）。
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from google.cloud import speech_v1 as speech

# 讲义语言 -> STT BCP-47 语言码
LANG_MAP = {"ja": "ja-JP", "en": "en-US", "zh": "cmn-Hans-CN"}

SAMPLE_RATE = 16000
STREAM_RESTART_SEC = 240.0  # 在 5 分钟硬上限前重启

OnText = Callable[[str], Awaitable[None]]


def lang_code(lecture_lang: str) -> str:
    return LANG_MAP.get(lecture_lang, "ja-JP")


async def run_stt(
    audio_queue: "asyncio.Queue[bytes | None]",
    lecture_lang: str,
    on_interim: OnText,
    on_final: OnText,
) -> None:
    """从 audio_queue 取音频喂给 STT，回调 interim / final 文本。

    队列收到 None 视为结束。会在 STREAM_RESTART_SEC 处自动重启流。
    """
    client = speech.SpeechAsyncClient()
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

    while not stopped:
        async def requests():
            nonlocal stopped
            yield speech.StreamingRecognizeRequest(streaming_config=streaming_config)
            start = loop.time()
            while loop.time() - start < STREAM_RESTART_SEC:
                chunk = await audio_queue.get()
                if chunk is None:
                    stopped = True
                    return
                yield speech.StreamingRecognizeRequest(audio_content=chunk)

        responses = await client.streaming_recognize(requests=requests())
        async for response in responses:
            for result in response.results:
                if not result.alternatives:
                    continue
                text = result.alternatives[0].transcript.strip()
                if not text:
                    continue
                if result.is_final:
                    await on_final(text)
                else:
                    await on_interim(text)
