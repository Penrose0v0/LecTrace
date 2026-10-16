"""Google Cloud Speech-to-Text **v1** 流式代理（default 模型；0.024 USD/分）。

前端把麦克风音频（16kHz / 16-bit / 单声道 LINEAR16 PCM）经 WebSocket 二进制帧上行，
后端把音频喂给 STT streaming API，产出 interim（临时）/ final（最终）识别结果。
凭证走 ADC（本地）/ 运行时服务账号（Cloud Run）。

流的重启 / 出错重试见 google_stream.py。v2 + Chirp 3 见 google_stt_v2.py。
"""

from __future__ import annotations

import asyncio

from google.cloud import speech_v1 as speech

from .google_stream import OnText, stream_loop

# 讲义语言 -> STT BCP-47 语言码
LANG_MAP = {"ja": "ja-JP", "en": "en-US", "zh": "cmn-Hans-CN"}

SAMPLE_RATE = 16000


def lang_code(lecture_lang: str) -> str:
    return LANG_MAP.get(lecture_lang, "ja-JP")


async def run_stt(
    audio_queue: "asyncio.Queue[bytes | None]",
    lecture_lang: str,
    on_interim: OnText,
    on_final: OnText,
) -> None:
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
    streaming_config = speech.StreamingRecognitionConfig(config=config, interim_results=True)
    await stream_loop(
        audio_queue, on_interim, on_final,
        streaming_recognize=lambda reqs: client.streaming_recognize(requests=reqs),
        config_request=lambda: speech.StreamingRecognizeRequest(streaming_config=streaming_config),
        audio_request=lambda chunk: speech.StreamingRecognizeRequest(audio_content=chunk),
        who="stt-v1",
    )
