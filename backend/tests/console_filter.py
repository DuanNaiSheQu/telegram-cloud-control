#!/usr/bin/env python3
"""批量重试类型过滤验收（需先起栈：./scripts/stack_local.sh up）：

    cd backend && .venv/bin/python -m tests.console_filter

覆盖：允许的 5 类 → ok:true；禁止的 6 类 → ok:false + 指定中文提示；
单条 retry 对 send_message 仍可用；混合批次只重排允许的那些。
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

BACKEND = pathlib.Path(os.environ.get("TGCC_BACKEND", "/Users/duannai/telegram云控/backend"))
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

BASE = "http://127.0.0.1:8000"
SUFFIX = uuid.uuid4().hex[:6]
MARK = f"类型过滤验证-{SUFFIX}"
PASSED: list[str] = []
FAILED: list[str] = []
STATE: dict[str, Any] = {}

ALLOWED = ["sync_dialogs", "sync_messages", "account_check", "update_profile", "relay_to_staff"]
BLOCKED = ["send_message", "login_start", "login_code", "login_password", "bot_reply", "reply_to_origin"]
BLOCKED_MESSAGE = "该任务类型不允许批量重试，请在任务详情里单独重试"


def check(name: str, ok: bool, detail: Any = "") -> None:
    print(("  ✅ " if ok else "  ❌ ") + name + (f" — {str(detail)[:180]}" if detail else ""))
    (PASSED if ok else FAILED).append(name)


class Api:
    def __init__(self) -> None:
        self.client = httpx.Client(base_url=BASE, timeout=30)
        self.token: Optional[str] = None

    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def request(self, method: str, url: str, **kw) -> httpx.Response:
        headers = dict(kw.pop("headers", {}) or {})
        headers.update(self.headers())
        return self.client.request(method, url, headers=headers, **kw)

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def post(self, url, **kw):
        return self.request("POST", url, **kw)

    def delete(self, url, **kw):
        return self.request("DELETE", url, **kw)


async def seed() -> None:
    from app import db
    from app.models import Task, TaskStatus, TaskType

    api = Api()
    api.token = api.post("/api/auth/login", json={"username": "admin", "password": "admin12345"}).json()["access_token"]
    account = api.post("/api/accounts", json={"phone": f"+113400{int(SUFFIX, 16) % 100000:05d}3", "remark": f"验证备注-{SUFFIX}"}).json()
    STATE["account"] = account["id"]
    api.client.close()

    async with db.SessionFactory() as session:
        now = datetime.now(tz=timezone.utc)
        ids: dict[str, str] = {}
        for type_name in ALLOWED + BLOCKED:
            task = Task(
                type=TaskType(type_name),
                status=TaskStatus.failed,
                account_id=uuid.UUID(account["id"]),
                payload={},
                attempts=3,
                max_attempts=5,
                error=MARK,
                next_run_at=now,
                completed_at=now,
                created_at=now,
            )
            session.add(task)
            await session.flush()
            ids[type_name] = str(task.id)
        # 混合批次专用：A 段会把允许类型都重排成 pending，这里单独留一条 failed
        mixed = Task(
            type=TaskType.account_check,
            status=TaskStatus.failed,
            account_id=uuid.UUID(account["id"]),
            payload={},
            attempts=2,
            max_attempts=5,
            error=MARK,
            next_run_at=now,
            completed_at=now,
            created_at=now,
        )
        session.add(mixed)
        await session.flush()
        ids["__mixed__"] = str(mixed.id)

        # 单独一条 send_message，用来验证「单条重试不受批量白名单限制」
        solo = Task(
            type=TaskType.send_message,
            status=TaskStatus.failed,
            account_id=uuid.UUID(account["id"]),
            payload={},
            attempts=5,
            max_attempts=5,
            error=MARK,
            next_run_at=now,
            completed_at=now,
            created_at=now,
        )
        session.add(solo)
        await session.flush()
        ids["__solo__"] = str(solo.id)
        STATE["ids"] = ids
        await session.commit()
    await db.dispose_engine()


async def cleanup() -> None:
    from sqlalchemy import delete, select

    from app import db
    from app.models import Task, TgAccount

    api = Api()
    login = api.post("/api/auth/login", json={"username": "admin", "password": "admin12345"})
    if login.status_code == 200:
        api.token = login.json()["access_token"]
        if STATE.get("account"):
            api.delete(f"/api/accounts/{STATE['account']}")
    api.client.close()

    async with db.SessionFactory() as session:
        await session.execute(delete(Task).where(Task.error == MARK))
        rows = list((await session.scalars(select(TgAccount).where(TgAccount.remark == f"验证备注-{SUFFIX}"))).all())
        for row in rows:
            await session.delete(row)
        await session.commit()
    await db.dispose_engine()


def main() -> int:
    api = Api()
    api.token = api.post("/api/auth/login", json={"username": "admin", "password": "admin12345"}).json()["access_token"]
    ids = STATE["ids"]

    print("A) 允许批量重试的 5 类")
    r = api.post("/api/tasks/bulk/retry", json={"task_ids": [ids[t] for t in ALLOWED]})
    body = r.json() if r.status_code == 200 else {}
    by_id = {i["task_id"]: i for i in body.get("results", [])}
    for type_name in ALLOWED:
        item = by_id.get(ids[type_name], {})
        check(f"{type_name} → 允许", item.get("ok") is True, item.get("message"))
    check(
        "5 类全部成功（succeeded=5, failed=0）",
        body.get("requested") == 5 and body.get("succeeded") == 5 and body.get("failed") == 0,
        {k: body.get(k) for k in ("requested", "succeeded", "failed")},
    )

    print("B) 禁止批量重试的 6 类")
    r = api.post("/api/tasks/bulk/retry", json={"task_ids": [ids[t] for t in BLOCKED]})
    body = r.json() if r.status_code == 200 else {}
    by_id = {i["task_id"]: i for i in body.get("results", [])}
    for type_name in BLOCKED:
        item = by_id.get(ids[type_name], {})
        check(
            f"{type_name} → 拒绝且提示固定",
            item.get("ok") is False and item.get("message") == BLOCKED_MESSAGE,
            item.get("message"),
        )
    check(
        "6 类全部被拦（succeeded=0, failed=6）",
        body.get("succeeded") == 0 and body.get("failed") == 6,
        {k: body.get(k) for k in ("requested", "succeeded", "failed")},
    )

    print("C) 被拦下的任务状态没被改动")
    r = api.get("/api/tasks", params={"type": "send_message", "status": "failed", "page_size": 50})
    still_failed = {i["id"] for i in r.json().get("items", [])}
    check("send_message 仍是 failed（没有偷偷重排）", ids["send_message"] in still_failed, f"failed={len(still_failed)}")

    print("D) 单条重试不受批量白名单限制")
    r = api.post(f"/api/tasks/{ids['__solo__']}/retry")
    check(
        "POST /api/tasks/{id}/retry 对 send_message 仍可用",
        r.status_code == 200 and r.json().get("task", {}).get("status") == "pending",
        f"HTTP {r.status_code} {r.json().get('message')}",
    )

    print("E) 混合批次：只重排允许的")
    mixed = [ids["__mixed__"], ids["send_message"], ids["login_code"], str(uuid.uuid4())]
    r = api.post("/api/tasks/bulk/retry", json={"task_ids": mixed})
    body = r.json() if r.status_code == 200 else {}
    messages = {i["task_id"]: i.get("message") for i in body.get("results", [])}
    check(
        "混合批次逐条给结果（1 成功 / 类型拦 2 + 不存在 1）",
        body.get("requested") == 4 and body.get("succeeded") == 1 and body.get("failed") == 3,
        {k: body.get(k) for k in ("requested", "succeeded", "failed")},
    )
    check("send_message 那条给的是类型提示", messages.get(ids["send_message"]) == BLOCKED_MESSAGE, messages.get(ids["send_message"]))
    check("login_code 那条也是类型提示", messages.get(ids["login_code"]) == BLOCKED_MESSAGE, messages.get(ids["login_code"]))

    r = api.get("/api/audit", params={"action": "task.bulk_retry", "page_size": 3})
    audit_items = r.json().get("items", []) if r.status_code == 200 else []
    check(
        "审计里能看到 blocked_types 计数",
        bool(audit_items) and isinstance(audit_items[0].get("detail", {}).get("blocked_types"), int),
        audit_items[0].get("detail") if audit_items else None,
    )

    print()
    print(f"== 结果：{len(PASSED)} 通过 / {len(FAILED)} 失败 ==")
    for item in FAILED:
        print("  FAIL:", item)
    return 1 if FAILED else 0


if __name__ == "__main__":
    try:
        asyncio.run(seed())
        code = main()
    finally:
        asyncio.run(cleanup())
        print("已清理类型过滤测试数据")
    sys.exit(code)
