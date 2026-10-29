"""线上验证域名迁移：模拟浏览器在旧域名已登录 → 申请票据 → 新域名兑换 → 同一 uid；重放失败；登出后不再自动登录。

  .venv/bin/python backend/tests/e2e_handoff.py https://lectrace-jngknpqwya-an.a.run.app https://lectrace.app
用本地 .env 的 SESSION_SECRET 签一个旧域名 cookie（和线上相同）。测试用户最后由调用方清理。
"""
from __future__ import annotations

import asyncio
import pathlib
import sys
import time

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app.auth import COOKIE_NAME, sign_session  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.models import User  # noqa: E402

OLD, NEW = sys.argv[1].rstrip("/"), sys.argv[2].rstrip("/")


async def main():
    s = get_settings()
    me = User(id="google:test-e2e", email="huyang0v0@gmail.com", name="e2e")
    old_cookie = sign_session(me, s)
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as c:
        # 1) 旧域名：后端告诉前端要迁移
        cfg = (await c.get(f"{OLD}/api/auth/config")).json()
        assert cfg["is_legacy"] is True and cfg["primary_origin"] == NEW, cfg
        cfg_new = (await c.get(f"{NEW}/api/auth/config")).json()
        assert cfg_new["is_legacy"] is False and cfg_new["host"] == NEW.split("//")[1], cfg_new
        print("1 config ok: old is_legacy, new not (no loop)")

        # 2) 旧域名已登录 → 申请票据（旧 cookie 不被清）
        r = await c.post(f"{OLD}/api/auth/handoff", json={"next": "/?from=old"}, cookies={COOKIE_NAME: old_cookie})
        assert r.status_code == 200, (r.status_code, r.text)
        assert COOKIE_NAME not in r.headers.get("set-cookie", "")
        url = r.json()["url"]
        assert url.startswith(f"{NEW}/auth/handoff?t=") and old_cookie not in url
        print("2 ticket ok:", url[:60] + "…")

        # 3) 新域名兑换：302 到 next，带新域名 cookie
        t0 = time.monotonic()
        r = await c.get(url)
        assert r.status_code == 302, (r.status_code, r.text[:200])
        assert r.headers["location"] in ("/?from=old", f"{NEW}/?from=old"), r.headers["location"]
        new_cookie = r.cookies.get(COOKIE_NAME)
        assert new_cookie, r.headers
        sc = r.headers["set-cookie"]
        assert "HttpOnly" in sc and "Secure" in sc and "Domain=" not in sc, sc
        assert r.headers.get("cache-control") == "no-store"
        print(f"3 redeem ok ({(time.monotonic()-t0)*1000:.0f} ms): 302 → {r.headers['location']}, host-only Secure HttpOnly cookie")

        # 4) 新 cookie 在新域名 = 同一 uid；旧 cookie 在旧域名仍有效
        me_new = (await c.get(f"{NEW}/api/auth/me", cookies={COOKIE_NAME: new_cookie})).json()
        assert me_new["user"]["id"] == me.id, me_new
        me_old = (await c.get(f"{OLD}/api/auth/me", cookies={COOKIE_NAME: old_cookie})).json()
        assert me_old["user"]["id"] == me.id
        print("4 uid preserved on new domain; old domain still logged in")

        # 5) 重放票据：失败，不发 cookie
        r = await c.get(url)
        assert r.status_code == 302 and r.headers["location"].endswith("/?handoff=expired"), r.headers
        assert COOKIE_NAME not in r.headers.get("set-cookie", "")
        print("5 replay rejected → /?handoff=expired, no cookie")

        # 6) 新域名登出 → 旧域名的旧 cookie 不能再换票据（403）→ 前端会不带票据跳转到登录页
        await asyncio.sleep(1.1)
        r = await c.post(f"{NEW}/api/auth/logout", cookies={COOKIE_NAME: new_cookie})
        assert r.status_code == 200
        r = await c.post(f"{OLD}/api/auth/handoff", json={"next": "/"}, cookies={COOKIE_NAME: old_cookie})
        assert r.status_code == 403 and r.json()["detail"]["code"] == "logged_out", (r.status_code, r.text)
        print("6 after logout on new domain: old cookie refused a ticket (403 logged_out)")

        # 7) 登出后重新登录（新签发的 cookie）→ 又能迁移
        await asyncio.sleep(1.1)
        fresh = sign_session(me, s)
        r = await c.post(f"{OLD}/api/auth/handoff", json={"next": "/"}, cookies={COOKIE_NAME: fresh})
        assert r.status_code == 200, r.text
        r = await c.get(r.json()["url"])
        assert r.status_code == 302 and r.cookies.get(COOKIE_NAME)
        print("7 fresh login migrates again")

        # 8) 新域名上不能申请票据；旧域名上不能兑换；伪造票据失败
        assert (await c.post(f"{NEW}/api/auth/handoff", json={"next": "/"}, cookies={COOKIE_NAME: fresh})).status_code == 404
        assert (await c.get(f"{OLD}/auth/handoff?t=abc")).status_code == 404
        r = await c.get(f"{NEW}/auth/handoff?t=forged&next=//evil.example")
        assert r.status_code == 302 and r.headers["location"].endswith("/?handoff=expired")
        print("8 wrong-domain and forged attempts rejected")

        # 9) 旧域名首页仍能打开（前端 JS 负责跳转）；新域名首页正常
        assert (await c.get(f"{OLD}/")).status_code == 200
        assert (await c.get(f"{NEW}/")).status_code == 200
        print("9 pages load on both domains")
    print("HANDOFF E2E OK")


asyncio.run(main())
