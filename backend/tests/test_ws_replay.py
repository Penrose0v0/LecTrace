"""转录 WebSocket 协议（内存后端 + 回放来源 + 本地开发登录）：session → segment… → end → 正常关闭帧。
`.venv/bin/python backend/tests/test_ws_replay.py`。需要 _archive/data 里有归档文件。"""
from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("STORE_BACKEND", "memory")

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.transcription import list_demo_sessions  # noqa: E402

s = get_settings()
s.store_backend = "memory"
s._auth_dev_login_env = "1"
s.google_client_id = ""
s.admin_emails = frozenset()
s.primary_host = ""
s.replay_speed = 200.0
s.replay_max_gap_sec = 0.05

files = list_demo_sessions(s.demo_data_dir)
assert files, f"没有归档文件：{s.demo_data_dir}"

with TestClient(app) as c:
    assert c.post("/api/auth/dev").status_code == 200
    r = c.post("/api/sessions", json={"title": "replay", "source": "replay", "file": files[0]["file"]})
    sid = r.json()["id"]
    types = []
    with c.websocket_connect(f"/ws/transcribe?session={sid}") as ws:
        while True:
            m = ws.receive_json()
            types.append(m["type"])
            if m["type"] == "end":
                break
            if m["type"] == "error":
                raise AssertionError(m)
        # end 之后服务端应发关闭帧（code 1000），而不是直接断连
        close = ws.receive()
        assert close["type"] == "websocket.close" and close.get("code") == 1000, close
    assert types[0] == "session" and types.count("segment") >= 3 and types[-1] == "end", types[:5]
    # 未登录 → error + 4401
    c.cookies.clear()
    with c.websocket_connect(f"/ws/transcribe?session={sid}") as ws:
        assert ws.receive_json()["code"] == "unauthorized"
        assert ws.receive()["code"] == 4401
print(f"ALL OK (segments={types.count('segment')})")
