"""FirestoreStore 的票据事务：对着本地模拟器跑（FIRESTORE_EMULATOR_HOST 必须已设置，防止误写生产库）。

  export JAVA_HOME=/opt/homebrew/opt/openjdk@17; firebase emulators:start --only firestore --project demo-lectrace
  FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 .venv/bin/python backend/tests/test_handoff_firestore.py
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

assert os.environ.get("FIRESTORE_EMULATOR_HOST"), "只允许对模拟器跑：请设置 FIRESTORE_EMULATOR_HOST"

from app.auth import new_handoff_ticket  # noqa: E402
from app.store.firestore import FirestoreStore  # noqa: E402


async def main():
    store = FirestoreStore(project="demo-lectrace")
    data = {"user": {"id": "google:1", "email": "a@b", "name": "A", "picture": ""}, "target": "lectrace.app"}

    # 1) 正常：一次成功，第二次 None
    _, h = new_handoff_ticket()
    await store.create_handoff(h, data, expires_at=time.time() + 60)
    assert (await store.redeem_handoff(h, time.time())) == data
    assert (await store.redeem_handoff(h, time.time())) is None
    print("ok firestore: single use")

    # 2) 过期
    _, h = new_handoff_ticket()
    await store.create_handoff(h, data, expires_at=time.time() - 1)
    assert (await store.redeem_handoff(h, time.time())) is None
    print("ok firestore: expired")

    # 3) 不存在
    assert (await store.redeem_handoff("0" * 64, time.time())) is None
    print("ok firestore: unknown ticket")

    # 4) 并发兑换：5 个事务同时来，恰好一个成功
    _, h = new_handoff_ticket()
    await store.create_handoff(h, data, expires_at=time.time() + 60)
    results = await asyncio.gather(*[store.redeem_handoff(h, time.time()) for _ in range(5)], return_exceptions=True)
    wins = [r for r in results if isinstance(r, dict)]
    errs = [r for r in results if isinstance(r, Exception)]
    assert len(wins) == 1, results
    assert not errs, errs  # 事务冲突由客户端库重试，不应抛到外面
    print("ok firestore: concurrent redeem → exactly one wins")

    # 5) 文档里没有明文票据，只有 sha256 作 id；ttl 字段存在
    snap = await store._handoff(h).get()
    d = snap.to_dict()
    assert d["used"] is True and "ttl" in d and len(snap.id) == 64
    print("ok firestore: stored by hash, ttl present")
    print("ALL OK")


asyncio.run(main())
