"""Google STT 流中途报错的自动重试（v1 / v2 共用 google_stream）。`.venv/bin/python backend/tests/test_stt_retry.py`"""
from __future__ import annotations

import asyncio
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from google.api_core import exceptions as gexc  # noqa: E402

from app.transcription import google_stream as gs  # noqa: E402
from app.transcription import google_stt as v1  # noqa: E402
from app.transcription import google_stt_v2 as v2  # noqa: E402

gs.STREAM_RETRY_DELAYS = (0.01, 0.01, 0.01, 0.01)
gs.STREAM_HEALTHY_SEC = 0.05


class Alt:
    def __init__(self, t): self.transcript = t
class Res:
    def __init__(self, t, final): self.alternatives = [Alt(t)]; self.is_final = final
class Resp:
    def __init__(self, t, final): self.results = [Res(t, final)]


def make_client(plan, audio_attr):
    calls = []

    class FakeClient:
        def __init__(self, *a, **k): pass

        async def streaming_recognize(self, requests):
            behavior = plan[min(len(calls), len(plan) - 1)]
            calls.append(behavior)

            async def gen():
                n, first = 0, True
                async for req in requests:
                    if first:
                        assert not getattr(req, audio_attr), "第一条请求应是配置"
                        first = False
                        continue
                    n += 1
                    if behavior == "fail" and n >= 2:
                        raise gexc.InvalidArgument("Request contains an invalid argument.")
                    if behavior == "ok":
                        yield Resp(f"seg{n}", True)
            return gen()

    return FakeClient, calls


async def feed(q, n):
    for _ in range(n):
        await q.put(b"\x00\x01" * 100)
        await asyncio.sleep(0.005)
    await q.put(None)


async def run(version, plan, n_chunks):
    if version == "v1":
        FakeClient, calls = make_client(plan, "audio_content")
        v1.speech.SpeechAsyncClient = FakeClient
        runner = lambda q, a, b: v1.run_stt(q, "ja", a, b)  # noqa: E731
    else:
        FakeClient, calls = make_client(plan, "audio")
        v2.SpeechAsyncClient = FakeClient
        runner = lambda q, a, b: v2.run_stt(q, "ja", a, b, project="p", location="us")  # noqa: E731
    q: asyncio.Queue = asyncio.Queue()
    finals = []
    async def on_final(t): finals.append(t)
    async def on_interim(t): pass
    feeder = asyncio.create_task(feed(q, n_chunks))
    try:
        await runner(q, on_interim, on_final)
    finally:
        feeder.cancel()
    return calls, finals


async def main():
    for version in ("v1", "v2"):
        calls, finals = await run(version, ["fail", "fail", "ok"], 40)
        assert calls[:3] == ["fail", "fail", "ok"] and finals, (calls, len(finals))
        try:
            await run(version, ["fail"], 200)
            raise AssertionError("应该抛错")
        except gexc.InvalidArgument:
            pass
        print(f"ok {version}: recovers after 2 failures; raises after retries exhausted")
    print("ALL OK")


asyncio.run(main())
