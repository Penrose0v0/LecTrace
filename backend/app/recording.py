"""录音保存：把前端上行的原始 PCM 流式写到 GCS（或本地目录）。

一次 WebSocket 连接 = 一个 take（暂停再继续就是下一个 take）。只存原始 PCM：
长度事先不知道而 GCS 对象不可修改，没法回填 WAV 头；回放时按对象大小拼个头即可。
每个 take 的采样率 / 对应转录时间轴的起点 t_offset 记进会话文档（见 store.add_recording），
以后做回放靠它和转录对齐。

写入在独立线程里进行（GCS 客户端是同步的），事件循环只负责往队列里丢字节。
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from pathlib import Path
from typing import BinaryIO

from .config import Settings

log = logging.getLogger("lectrace.recording")

_SENTINEL = b""


class Recorder:
    """一个 take 的写入器。write() 不阻塞；close() 等待写完并返回元信息。"""

    def __init__(self, sink: BinaryIO, path: str, sample_rate: int, t_offset: float) -> None:
        self._sink = sink
        self._q: queue.Queue[bytes] = queue.Queue()
        self._bytes = 0
        self._error: Exception | None = None
        self.info = {
            "path": path,
            "sample_rate": sample_rate,
            "channels": 1,
            "sample_width": 2,
            "t_offset": t_offset,
            "started_at": time.time(),
        }
        self._thread = threading.Thread(target=self._run, name="recorder", daemon=True)
        self._thread.start()

    def write(self, chunk: bytes) -> None:
        if chunk and self._error is None:
            self._q.put(chunk)

    def _run(self) -> None:
        try:
            while True:
                chunk = self._q.get()
                if chunk is _SENTINEL:
                    break
                self._sink.write(chunk)
                self._bytes += len(chunk)
        except Exception as exc:  # noqa: BLE001 - 录音失败不影响转录
            self._error = exc
            log.exception("recording write failed")
        finally:
            try:
                self._sink.close()
            except Exception:  # noqa: BLE001
                log.exception("recording close failed")

    def close_blocking(self) -> dict | None:
        """阻塞直到写完；成功返回元信息，失败返回 None。请放到线程里 await。"""
        self._q.put(_SENTINEL)
        self._thread.join()
        if self._error is not None:
            return None
        bps = self.info["sample_rate"] * self.info["channels"] * self.info["sample_width"]
        return {**self.info, "bytes": self._bytes, "duration_sec": self._bytes / bps}


def delete_recordings(settings: Settings, infos: list[dict]) -> None:
    """删掉一组 take 的音频文件（阻塞，放到线程里调）。单个失败只记日志。"""
    client = None
    for info in infos:
        path = str(info.get("path", ""))
        try:
            if path.startswith("gs://"):
                from google.cloud import storage

                client = client or storage.Client()
                bucket, _, name = path[len("gs://"):].partition("/")
                client.bucket(bucket).blob(name).delete()
            elif path:
                (settings.recordings_dir / path).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            log.exception("delete recording failed: %s", path)


def open_recorder(
    settings: Settings, session_id: str, take: int, sample_rate: int, t_offset: float
) -> Recorder | None:
    """按配置打开一个 take 的写入器；RECORDINGS=off 或打开失败时返回 None。"""
    name = f"sessions/{session_id}/take-{take:03d}.pcm"
    try:
        if settings.recordings == "local":
            path = settings.recordings_dir / name
            path.parent.mkdir(parents=True, exist_ok=True)
            return Recorder(path.open("wb"), str(path.relative_to(settings.recordings_dir)), sample_rate, t_offset)
        if settings.recordings == "gcs":
            from google.cloud import storage

            if not settings.recordings_bucket:
                log.warning("RECORDINGS=gcs 但未设置 RECORDINGS_BUCKET，跳过录音")
                return None
            blob = storage.Client().bucket(settings.recordings_bucket).blob(name)
            # 可续传分块上传：内存里只保留一个 chunk
            sink = blob.open("wb", chunk_size=8 * 1024 * 1024, content_type="application/octet-stream")
            return Recorder(sink, f"gs://{settings.recordings_bucket}/{name}", sample_rate, t_offset)
    except Exception:  # noqa: BLE001
        log.exception("open recorder failed")
    return None
