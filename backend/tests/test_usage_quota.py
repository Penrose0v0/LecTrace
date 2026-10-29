"""用量记录 + 对话配额 + 管理后台接口（内存后端 + 假 LLM）。`.venv/bin/python backend/tests/test_usage_quota.py`"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("STORE_BACKEND", "memory")

import httpx  # noqa: E402

from app import ai as ai_mod  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.deps import get_store  # noqa: E402
from app.llm.base import LLMUsage  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Segment  # noqa: E402
from app.usage import day_key  # noqa: E402

s = get_settings()
s.store_backend = "memory"
s.admin_emails = frozenset({"boss@example.com"})  # dev 用户不是管理员 → 受配额
s.quota_max_chats_per_day = 2
s.quota_max_lectures_per_day = 0
s.llm_provider = "siliconflow"
s.siliconflow_api_key = "fake"
s.llm_price_input_per_m = 1.0
s.llm_price_output_per_m = 2.0
s._auth_dev_login_env = "1"
s.google_client_id = ""
s.primary_host = ""


class FakeLLM:
    name, model = "fake", "fake-model"

    async def stream(self, messages, *, max_tokens, temperature, thinking=False, usage: LLMUsage | None = None):
        for w in ("hello ", "world"):
            yield w
        if usage is not None:
            usage.set(1000, 50)


ai_mod.get_llm = lambda settings: FakeLLM()


async def main():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/auth/dev")
        assert r.status_code == 200, r.text
        q = r.json()["quota"]
        assert q["max_chats_per_day"] == 2 and q["chats_today"] == 0, q
        assert (await c.get("/api/admin/users")).status_code == 403

        sid = (await c.post("/api/sessions", json={"title": "t"})).json()["id"]
        store = get_store()
        for i in range(3):
            await store.append(sid, Segment(seq=i + 1, text=f"seg {i}", t=10.0 * (i + 1)))

        r = await c.post("/api/catchup", json={"session_id": sid})
        assert r.status_code == 200 and "done" in r.text, r.text
        for i in range(2):
            r = await c.post("/api/chat", json={"session_id": sid, "message": f"q{i}"})
            assert r.status_code == 200 and "event: done" in r.text, (i, r.text)
        r = await c.post("/api/chat", json={"session_id": sid, "message": "q3"})
        assert r.status_code == 429 and r.json()["detail"]["code"] == "quota_chats_per_day", r.text
        assert (await c.get("/api/auth/me")).json()["quota"]["chats_today"] == 2

        s.admin_emails = frozenset({"dev@localhost"})
        d = (await c.get("/api/admin/users")).json()
        u = d["users"][0]
        assert u["email"] == "dev@localhost" and u["login_count"] == 1, u
        assert u["usage"]["chats"] == 2 and u["usage"]["catchups"] == 1 and u["usage"]["lectures"] == 1, u["usage"]
        assert u["usage"]["llm_in_tokens"] == 3000 and u["usage"]["llm_out_tokens"] == 150
        assert abs(u["usage"]["llm_cost"] - (3000 * 1 + 150 * 2) / 1e6) < 1e-9
        assert d["today"] == day_key(s)
        dd = (await c.get(f"/api/admin/users/{u['id']}")).json()
        assert len(dd["days"]) == 1 and dd["days"][0]["chats"] == 2 and len(dd["events"]) == 3
        for i in range(3):  # 管理员不受配额
            assert (await c.post("/api/chat", json={"session_id": sid, "message": f"a{i}"})).status_code == 200
        assert (await c.get("/admin.html")).status_code == 200
    print("ALL OK")


asyncio.run(main())
