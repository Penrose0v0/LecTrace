"""Google Cloud Speech-to-Text **v2** 流式代理，默认 Chirp 3（0.016 USD/分，比 v1 便宜三分之一）。

和 v1 的差别：
- 走区域端点 `{location}-speech.googleapis.com`，recognizer 用隐式的 `.../recognizers/_`，不用预建。
- 2026-10 实测：chirp_3 的日语在 asia-northeast1 被拒（"no longer generally available in region"），
  us / eu 可用，所以默认 GOOGLE_STT_V2_LOCATION=us，音频会送到美国处理。Tokyo 只有 long / short / telephony。
- chirp_3 的 interim 很稀（60 秒里 4 条，且只在 final 前几秒出现），final 在自然停顿处每 3–12 秒一条；
  转录质量比 v1 default 明显通顺。界面上「正在识别」的灰字预览会少很多，不影响 Catch-up。
- 每条流内单个音频请求上限 25 KB（前端一帧 ~2.7 KB，够用）。

流的重启 / 出错重试见 google_stream.py。
"""

from __future__ import annotations

import asyncio

from google.api_core.client_options import ClientOptions
from google.cloud.speech_v2 import SpeechAsyncClient
from google.cloud.speech_v2.types import cloud_speech as cs

from .google_stream import OnText, stream_loop
from .google_stt import LANG_MAP, SAMPLE_RATE

__all__ = ["SAMPLE_RATE", "run_stt"]


def lang_code(lecture_lang: str) -> str:
    return LANG_MAP.get(lecture_lang, "ja-JP")


async def run_stt(
    audio_queue: "asyncio.Queue[bytes | None]",
    lecture_lang: str,
    on_interim: OnText,
    on_final: OnText,
    *,
    project: str,
    location: str = "us",
    model: str = "chirp_3",
) -> None:
    if not project:
        raise RuntimeError("Google STT v2 需要 GCP_PROJECT（recognizer 路径里要带项目 ID）。")
    try:
        opts = ClientOptions(api_endpoint=f"{location}-speech.googleapis.com") if location != "global" else None
        client = SpeechAsyncClient(client_options=opts)
    except Exception as exc:  # noqa: BLE001 - 本地多半是没配 ADC
        raise RuntimeError(
            "Google STT 需要 GCP 凭证：本地请先 `gcloud auth application-default login`，"
            "或在课堂设置里把音频来源改成 OpenAI。"
        ) from exc
    config = cs.RecognitionConfig(
        explicit_decoding_config=cs.ExplicitDecodingConfig(
            encoding=cs.ExplicitDecodingConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=SAMPLE_RATE,
            audio_channel_count=1,
        ),
        language_codes=[lang_code(lecture_lang)],
        model=model,
        features=cs.RecognitionFeatures(enable_automatic_punctuation=True),
    )
    streaming_config = cs.StreamingRecognitionConfig(
        config=config,
        streaming_features=cs.StreamingRecognitionFeatures(interim_results=True),
    )
    recognizer = f"projects/{project}/locations/{location}/recognizers/_"
    await stream_loop(
        audio_queue, on_interim, on_final,
        streaming_recognize=lambda reqs: client.streaming_recognize(requests=reqs),
        config_request=lambda: cs.StreamingRecognizeRequest(recognizer=recognizer, streaming_config=streaming_config),
        audio_request=lambda chunk: cs.StreamingRecognizeRequest(audio=chunk),
        who=f"stt-v2/{model}@{location}",
    )
