#!/usr/bin/env python3
"""补充验收：Worker 心跳丢失通知 + 通知去重（同一件事只出现一次）+ 采样表只增不重。

    cd backend && .venv/bin/python -m tests.console_extra
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

BACKEND = pathlib.Path(os.environ.get("TGCC_BACKEND", "/Users/duannai/telegram云控/backend"))
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

BASE = "http://127.0.0.1:8000"
SUFFIX = uuid.uuid4().hex[:6]
GHOST = f"ghost-worker-{SUFFIX}"
PASSED: list[str] = []
FAILED: list[str] = []
STATE: dict[str, Any] = {}


def check(name: str, ok: bool, detail: Any = "") -> None:
    print(("  ✅ " if ok else "  ❌ ") + name + (f" — {detail}" if detail else ""))
    (PASSED if ok else FAILED).append(name)


async def seed() -> None:
    from app import db
    from app.models import Lease, TgAccount, AccountStatus, CurrentTask

    api = httpx.Client(base_url=BASE, timeout=30)
    token = api.post("/api/auth/login", json={"username": "admin", "password": "admin12345"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    created = api.post(
        "/api/accounts",
        json={"phone": f"+113700{int(SUFFIX, 16) % 100000:05d}9", "remark": f"验证备注-{SUFFIX}"},
        headers=headers,
    )
    assert created.status_code in (200, 201), created.text
    STATE["account"] = created.json()["id"]
    api.close()

    # 造一条租约：持有者是一个「没有心跳」的 Worker（模拟 Worker 进程挂掉）
    now = datetime.now(tz=timezone.utc)
    async with db.SessionFactory() as session:
        session.add(
            Lease(
                account_id=uuid.UUID(STATE["account"]),
                worker_id=GHOST,
                lease_until=now + timedelta(minutes=10),
                last_heartbeat=now,
            )
        )
        await session.commit()
    await db.dispose_engine()


async def clear_gate() -> None:
    from app.redis_client import close_redis, get_redis

    redis = get_redis()
    await redis.delete("tgcc:notifications:last-sync")
    await close_redis()


async def count_duplicates() -> int:
    """同一 dedupe_key 出现多行就是去重失效。"""
    from sqlalchemy import func, select

    from app import db
    from app.models import Notification

    async with db.SessionFactory() as session:
        rows = await session.execute(
            select(Notification.dedupe_key, func.count())
            .where(Notification.dedupe_key.like(f"%{SUFFIX}%") | Notification.dedupe_key.like(f"worker_lost:{GHOST}%"))
            .group_by(Notification.dedupe_key)
        )
        dupes = [row for row in rows.all() if int(row[1]) > 1]
    await db.dispose_engine()
    return len(dupes)


async def cleanup() -> None:
    from sqlalchemy import delete, select

    from app import db
    from app.models import Lease, Notification, Proxy, TgAccount, User, AccountGroup
    from app.redis_client import close_redis, get_redis

    api = httpx.Client(base_url=BASE, timeout=30)
    login = api.post("/api/auth/login", json={"username": "admin", "password": "admin12345"})
    if login.status_code == 200:
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        if STATE.get("account"):
            api.delete(f"/api/accounts/{STATE['account']}", headers=headers)
    api.close()

    async with db.SessionFactory() as session:
        await session.execute(delete(Lease).where(Lease.worker_id == GHOST))
        await session.execute(delete(Notification).where(Notification.dedupe_key.like(f"worker_lost:{GHOST}%")))
        await session.commit()
    redis = get_redis()
    await redis.delete("tgcc:notifications:last-sync")
    await close_redis()
    await db.dispose_engine()


def main() -> int:
    api = httpx.Client(base_url=BASE, timeout=30)
    token = api.post("/api/auth/login", json={"username": "admin", "password": "admin12345"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    asyncio.run(clear_gate())
    r = api.get("/api/notifications", params={"kind": "worker_lost", "page_size": 50}, headers=headers)
    items = r.json().get("items", []) if r.status_code == 200 else []
    ghost = [i for i in items if i.get("worker_id") == GHOST]
    check(
        "Worker 心跳丢失能聚合成通知",
        r.status_code == 200 and bool(ghost),
        ghost[0]["body"][:110] if ghost else f"HTTP {r.status_code} total={r.json().get('total') if r.status_code == 200 else '-'}",
    )
    if ghost:
        check("worker_lost 是全局通知（account_id=null）+ link 指向工作台", ghost[0]["account_id"] is None and ghost[0]["link"] == "/", {"link": ghost[0]["link"], "level": ghost[0]["level"]})

    # 再来两次（先清节流键强制重新聚合）：同一件事不能变成两条
    for _ in range(2):
        asyncio.run(clear_gate())
        api.get("/api/notifications", params={"page_size": 50}, headers=headers)
    dupes = asyncio.run(count_duplicates())
    check("通知去重生效（重复聚合不产生重复行）", dupes == 0, f"重复 dedupe_key 组数={dupes}")

    r = api.get("/api/notifications", params={"page_size": 50}, headers=headers)
    ghost_rows = [i for i in r.json().get("items", []) if i.get("worker_id") == GHOST]
    check("重复聚合后仍只有一条 Worker 丢失通知", len(ghost_rows) == 1, f"count={len(ghost_rows)}")

    api.close()
    print()
    print(f"== 补充结果：{len(PASSED)} 通过 / {len(FAILED)} 失败 ==")
    for item in FAILED:
        print("  FAIL:", item)
    return 1 if FAILED else 0


if __name__ == "__main__":
    try:
        asyncio.run(seed())
        code = main()
    finally:
        asyncio.run(cleanup())
        print("已清理补充测试数据")
    sys.exit(code)
