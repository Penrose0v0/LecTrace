"""域名迁移（handoff）测试：内存后端 + 本地开发登录，直接跑 `.venv/bin/python backend/tests/test_handoff.py`。

覆盖：开关关闭时 404 / 不跳转；可信转发头（共享密钥）；票据一次性、过期、host 不符；next 开放重定向；
cookie 在新域名生效且 uid 不变；旧域名 cookie 不被清除；登出互不影响；并发兑换只成功一次。
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("STORE_BACKEND", "memory")

import httpx  # noqa: E402

from app import auth as auth_mod  # noqa: E402
from app.auth import COOKIE_NAME, safe_next  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.deps import get_store  # noqa: E402
from app.main import app  # noqa: E402

OLD = "lectrace-jngknpqwya-an.a.run.app"
NEW = "lectrace.app"
SECRET = "proxy-secret-for-tests"

s = get_settings()
s.store_backend = "memory"
s._auth_dev_login_env = "1"
s.google_client_id = ""
s.admin_emails = frozenset()
s.session_secret = "test-session-secret"
s.proxy_shared_secret = SECRET
s.legacy_hosts = frozenset({OLD})
s.handoff_ttl_sec = 60


def via_worker(host: str) -> dict:
    """模拟经 Cloudflare Worker 转发：Host 是 run.app，真实域名在 X-Forwarded-Host，带共享密钥。"""
    return {"host": OLD, "x-forwarded-host": host, "x-proxy-auth": SECRET, "x-forwarded-proto": "https"}


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t", follow_redirects=False)


def test_safe_next():
    assert safe_next("/") == "/"
    assert safe_next("/admin.html?x=1") == "/admin.html?x=1"
    assert safe_next(None) == "/"
    for bad in ("//evil.com", "/\\evil.com", "https://evil.com", "evil.com", "/a\nb", "/a b", "/日本語", "/" + "x" * 3000):
        assert safe_next(bad) == "/", bad
    print("ok safe_next")


async def test_disabled():
    s.primary_host = ""
    async with client() as c:
        r = await c.get("/api/auth/config", headers=via_worker(OLD))
        assert r.json()["is_legacy"] is False and r.json()["primary_origin"] == ""
        await c.post("/api/auth/dev")
        assert (await c.post("/api/auth/handoff", json={"next": "/"}, headers=via_worker(OLD))).status_code == 404
        assert (await c.get("/auth/handoff?t=x", headers=via_worker(NEW))).status_code == 404
    print("ok disabled: 404 everywhere, no redirect hints")


async def test_public_host_trust():
    s.primary_host = NEW
    async with client() as c:
        # 没密钥的伪造转发头：按 Host（run.app）判断 → 旧域名
        r = await c.get("/api/auth/config", headers={"host": OLD, "x-forwarded-host": NEW})
        assert r.json()["is_legacy"] is True
        # 密钥错也不信
        r = await c.get("/api/auth/config", headers={"host": OLD, "x-forwarded-host": NEW, "x-proxy-auth": "wrong"})
        assert r.json()["is_legacy"] is True
        # 密钥对：信转发头 → 新域名
        r = await c.get("/api/auth/config", headers=via_worker(NEW))
        assert r.json()["is_legacy"] is False and r.json()["primary_origin"] == "https://lectrace.app"
        # 不是旧域名列表里的 host（例如 localhost）也不迁移
        r = await c.get("/api/auth/config", headers=via_worker("localhost:8000"))
        assert r.json()["is_legacy"] is False
    print("ok proxy header trust")


async def login_old(c: httpx.AsyncClient) -> str:
    r = await c.post("/api/auth/dev", headers=via_worker(OLD))
    assert r.status_code == 200
    return r.cookies[COOKIE_NAME]


async def test_happy_path():
    s.primary_host = NEW
    async with client() as c:
        old_cookie = await login_old(c)
        c.cookies.clear()
        r = await c.post("/api/auth/handoff", json={"next": "/?session=abc"},
                         headers=via_worker(OLD), cookies={COOKIE_NAME: old_cookie})
        assert r.status_code == 200, r.text
        assert r.headers["cache-control"] == "no-store"
        assert COOKIE_NAME not in r.headers.get("set-cookie", ""), "创建票据不能动旧域名 cookie"
        url = r.json()["url"]
        assert url.startswith("https://lectrace.app/auth/handoff?t=") and "next=%2F%3Fsession%3Dabc" in url
        assert old_cookie not in url and "ya29" not in url
        path = url[len("https://lectrace.app"):]
        # 新域名兑换：无 cookie 进来，302 到 next，带新 cookie
        r = await c.get(path, headers=via_worker(NEW))
        assert r.status_code == 302 and r.headers["location"] == "/?session=abc", (r.status_code, r.headers)
        assert r.headers["cache-control"] == "no-store" and r.headers["referrer-policy"] == "no-referrer"
        new_cookie = r.cookies[COOKIE_NAME]
        assert "HttpOnly" in r.headers["set-cookie"] and "Secure" in r.headers["set-cookie"]
        # 新 cookie 在新域名上是同一个用户
        c.cookies.clear()
        me = (await c.get("/api/auth/me", headers=via_worker(NEW), cookies={COOKIE_NAME: new_cookie})).json()
        assert me["user"]["id"] == "dev:local", me
        # 旧 cookie 在旧域名仍有效（两边各自登录）
        me_old = (await c.get("/api/auth/me", headers=via_worker(OLD), cookies={COOKIE_NAME: old_cookie})).json()
        assert me_old["user"]["id"] == "dev:local"
        # 票据第二次兑换：失败，不下发 cookie
        r = await c.get(path, headers=via_worker(NEW))
        assert r.status_code == 302 and r.headers["location"] == "/?handoff=expired"
        assert COOKIE_NAME not in r.headers.get("set-cookie", "")
        # 新域名登出不影响旧域名
        r = await c.post("/api/auth/logout", headers=via_worker(NEW), cookies={COOKIE_NAME: new_cookie})
        assert 'lt_session=""' in r.headers["set-cookie"] or "Max-Age=0" in r.headers["set-cookie"]
        me_old = (await c.get("/api/auth/me", headers=via_worker(OLD), cookies={COOKIE_NAME: old_cookie})).json()
        assert me_old["user"]["id"] == "dev:local"
    print("ok happy path: migrate, uid preserved, one-time, independent logout")


async def test_rejections():
    s.primary_host = NEW
    async with client() as c:
        old_cookie = await login_old(c)
        c.cookies.clear()
        hdr_old, ck = via_worker(OLD), {COOKIE_NAME: old_cookie}
        # 未登录不能申请票据
        assert (await c.post("/api/auth/handoff", json={"next": "/"}, headers=hdr_old)).status_code == 401
        # 在新域名上不能申请票据
        assert (await c.post("/api/auth/handoff", json={"next": "/"}, headers=via_worker(NEW), cookies=ck)).status_code == 404
        # 在旧域名上不能兑换
        assert (await c.get("/auth/handoff?t=abc", headers=hdr_old)).status_code == 404
        # 伪造 / 空 / 超长票据
        for t in ("", "nope", "x" * 200):
            r = await c.get(f"/auth/handoff?t={t}", headers=via_worker(NEW))
            assert r.status_code == 302 and r.headers["location"] == "/?handoff=expired" and COOKIE_NAME not in r.headers.get("set-cookie", "")
        # 开放重定向：next 被替换成 /
        r = await c.post("/api/auth/handoff", json={"next": "//evil.com/x"}, headers=hdr_old, cookies=ck)
        assert "next=%2F&" in r.json()["url"] + "&" or r.json()["url"].endswith("next=%2F")
        path = r.json()["url"][len("https://lectrace.app"):] + "&next=https://evil.com"  # 兑换时再塞一次也无效
        r = await c.get(path, headers=via_worker(NEW))
        assert r.status_code == 302 and r.headers["location"] == "/"
        # 过期：把票据时间拨回去
        r = await c.post("/api/auth/handoff", json={"next": "/"}, headers=hdr_old, cookies=ck)
        path = r.json()["url"][len("https://lectrace.app"):]
        store = get_store()
        for tkt in store._handoffs.values():
            tkt["expires_at"] -= 61
        r = await c.get(path, headers=via_worker(NEW))
        assert r.headers["location"] == "/?handoff=expired"
        # host 不符：票据目标是 lectrace.app，却在另一个（被当作 primary 的）host 兑换 → 拒绝
        r = await c.post("/api/auth/handoff", json={"next": "/"}, headers=hdr_old, cookies=ck)
        path = r.json()["url"][len("https://lectrace.app"):]
        s.primary_host = "other.example"
        r = await c.get(path, headers=via_worker("other.example"))
        assert r.headers["location"] == "/?handoff=expired" and COOKIE_NAME not in r.headers.get("set-cookie", "")
        s.primary_host = NEW
    print("ok rejections: unauth, wrong host, bad/expired/forged tickets, open redirect")


async def test_concurrent_redeem():
    s.primary_host = NEW
    async with client() as c:
        old_cookie = await login_old(c)
        c.cookies.clear()
        r = await c.post("/api/auth/handoff", json={"next": "/"}, headers=via_worker(OLD), cookies={COOKIE_NAME: old_cookie})
        path = r.json()["url"][len("https://lectrace.app"):]
        rs = await asyncio.gather(*[c.get(path, headers=via_worker(NEW)) for _ in range(5)])
        ok = [x for x in rs if x.headers["location"] == "/"]
        assert len(ok) == 1 and all(x.headers["location"] == "/?handoff=expired" for x in rs if x not in ok)
    print("ok concurrent redeem: exactly one succeeds")


async def test_regression_untouched():
    """开关关闭时，原有登录 / 建课 / 偏好流程一切照旧。"""
    s.primary_host = ""
    async with client() as c:
        r = await c.post("/api/auth/dev")
        assert r.status_code == 200 and r.json()["user"]["id"] == "dev:local"
        r = await c.post("/api/sessions", json={"title": "t"})
        assert r.status_code == 200
        r = await c.put("/api/me/prefs", json={"ui_language": "zh", "lecture_language": "ja", "window_minutes": 3, "theme": "dark"})
        assert r.status_code == 200
        r = await c.get("/")
        assert r.status_code == 200
    print("ok regression: existing auth/API unaffected with feature off")


async def main():
    test_safe_next()
    await test_disabled()
    await test_public_host_trust()
    await test_happy_path()
    await test_rejections()
    await test_concurrent_redeem()
    await test_regression_untouched()
    print("ALL OK")


if __name__ == "__main__":
    asyncio.run(main())
