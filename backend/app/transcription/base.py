"""转录源接口。

一个转录源就是一个异步生成器：不断产出 Segment。demo 用 ReplaySource；
之后接 Google Cloud Speech-to-Text 时，实现一个 GoogleSTTSource（把前端经
WebSocket 上行的音频转发给 streaming API，产出识别结果）即可，上层不变。
"""

from __future__ import annotations

from typing import AsyncIterator, Protocol

from ..models import Segment

Transcript = AsyncIterator[Segment]


class TranscriptionSource(Protocol):
    def stream(self) -> Transcript:
        """产出转录段落的异步流。"""
        ...
