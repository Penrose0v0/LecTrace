"""Google STT 流式代理的公共骨架（v1 / v2 共用）。

两个版本的差别只在：怎么建客户端、第一条配置请求长什么样、音频请求长什么样。
响应结构相同（results[].alternatives[0].transcript + is_final）。这里负责：

- 单条流约有 5 分钟上限：在 STREAM_RESTART_SEC 处主动收尾、开新流，音频持续入队不丢。
- 流中途出错（实测见过 v1 的 INVALID_ARGUMENT "Request contains an invalid argument."，音频正常、
  几分钟后又好了，像是服务端瞬时问题）：丢掉积压音频、稍等后开新流继续；连续失败超过
  STREAM_MAX_RETRIES 次才真正报错。
- 空帧不发（服务端会当成非法请求）。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator, Awaitable, Callable

from google.api_core import exceptions as gexc

log = logging.getLogger("lectrace.stt")

STREAM_RESTART_SEC = 240.0  # 在 5 分钟硬上限前重启
# 流中途出错后的重试：连续失败次数上限 + 每次重开前等待（秒）
STREAM_MAX_RETRIES = 4
STREAM_RETRY_DELAYS = (0.5, 1.0, 2.0, 4.0)
# 一条流活过这么久（秒）就认为服务是好的，连续失败计数清零
STREAM_HEALTHY_SEC = 20.0

OnText = Callable[[str], Awaitable[None]]
# 给定请求流，返回响应流（即 client.streaming_recognize(requests=...)）
StreamingRecognize = Callable[[AsyncIterator[Any]], Awaitable[AsyncIterator[Any]]]


def _drain(q: "asyncio.Queue[bytes | None]") -> bool:
    """丢掉队列里积压的音频（重开流前用，避免一口气灌进去）。遇到结束标记返回 True。"""
    while True:
        try:
            item = q.get_nowait()
        except asyncio.QueueEmpty:
            return False
        if item is None:
            return True


async def stream_loop(
    audio_queue: "asyncio.Queue[bytes | None]",
    on_interim: OnText,
    on_final: OnText,
    *,
    streaming_recognize: StreamingRecognize,
    config_request: Callable[[], Any],
    audio_request: Callable[[bytes], Any],
    who: str,
) -> None:
    """从 audio_queue 取音频喂给 STT，回调 interim / final 文本。队列收到 None 视为结束。"""
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
            yield config_request()
            while loop.time() - start < STREAM_RESTART_SEC:
                chunk = await audio_queue.get()
                if chunk is None:
                    stopped = True
                    return
                if not chunk:
                    continue
                stats["chunks"] += 1
                stats["bytes"] += len(chunk)
                stats["last"] = len(chunk)
                yield audio_request(chunk)

        try:
            responses = await streaming_recognize(requests())
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
                "%s stream #%d failed after %.1fs (chunks=%d bytes=%d last=%d results=%d): %s %s"
                " — retry %d/%d",
                who, stream_no, age, stats["chunks"], stats["bytes"], stats["last"], stats["results"],
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
