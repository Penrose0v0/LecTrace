"""线上冒烟：登录态 / 历史 / 转录 WebSocket / 录音落盘，走指定域名（run.app 或 lectrace.app）。

用本地 .env 的 SESSION_SECRET 签一个管理员 cookie（和线上相同），所以不需要浏览器 Google 登录。
  .venv/bin/python backend/tests/e2e_smoke.py https://lectrace.app [clip.pcm]
clip.pcm：16 kHz 单声道 s16le；不给就发 8 秒静音（只验证链路，不验证识别）。
测试建的课最后会删除。
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys
import time

import httpx
import websockets

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app.auth import COOKIE_NAME, sign_session  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.models import User  # noqa: E402

BASE = sys.argv[1].rstrip("/")
CLIP = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else None
CHUNK = 2730


async def main():
    s = get_settings()
    assert s.session_secret, "本地 .env 没有 SESSION_SECRET"
    me = User(id="google:test-e2e", email="huyang0v0@gmail.com", name="e2e")
    headers = {"Cookie": f"{COOKIE_NAME}={sign_session(me, s)}"}
    async with httpx.AsyncClient(base_url=BASE, headers=headers, timeout=30, follow_redirects=False) as c:
        h = (await c.get("/api/health")).json()
        print("health:", h["status"], h["transcription_source"], h["store_backend"])
        r = await c.get("/api/auth/config")
        print("config:", r.json())
        r = await c.get("/api/auth/me")
        assert r.json()["user"]["id"] == me.id, r.text
        print("login ok (cookie accepted on", BASE + ")")
        r = await c.get("/api/sessions")
        print("history ok:", len(r.json()["sessions"]), "sessions for test user")
        r = await c.post("/api/sessions", json={"title": "e2e smoke", "lecture_language": "ja"})
        assert r.status_code == 200, r.text
        sid = r.json()["id"]
        audio = CLIP.read_bytes() if CLIP else b"\x00" * (16000 * 2 * 8)
        segs, errors, t0 = [], [], time.monotonic()
        try:
            async with websockets.connect(
                f"{BASE.replace('https', 'wss')}/ws/transcribe?session={sid}", additional_headers=headers, max_size=None
            ) as ws:
                async def send():
                    for i in range(0, len(audio), CHUNK):
                        await ws.send(audio[i:i + CHUNK])
                        await asyncio.sleep(CHUNK / 32000)
                    await ws.send("stop")

                async def recv():
                    async for raw in ws:
                        m = json.loads(raw)
                        if m["type"] == "segment":
                            segs.append(m); print(f"  [{time.monotonic()-t0:4.1f}s] seg{m['seq']} {m['text'][:40]}")
                        elif m["type"] in ("error", "limit"):
                            errors.append(m); print("  !!", m)
                        elif m["type"] == "end":
                            return
                        elif m["type"] == "session":
                            print("  ws session:", m["source"], "resumed=", m["resumed"])

                await asyncio.gather(send(), recv())
            info = (await c.get(f"/api/sessions/{sid}")).json()["session"]
            recs = info.get("recordings", [])
            print(f"ws done {time.monotonic()-t0:.1f}s segments={len(segs)} errors={errors} recordings={[(r['path'].split('/')[-1], round(r['duration_sec'])) for r in recs]}")
            assert not errors
            assert recs, "录音没有落盘"
            if CLIP:
                assert segs, "有音频但没有识别出段落"
        finally:
            r = await c.delete(f"/api/sessions/{sid}")
            print("cleanup:", r.status_code)
    print("SMOKE OK", BASE)


asyncio.run(main())
