#!/usr/bin/env python3
"""第二轮验收：删除回归 / 审计时间范围 / 任务批量重试 / 转发测试消息 / 转发记录新字段。

    cd backend && .venv/bin/python -m tests.console_delete
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

BACKEND = pathlib.Path(os.environ.get("TGCC_BACKEND", "/Users/duannai/telegram云控/backend"))
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

BASE = "http://127.0.0.1:8000"
SUFFIX = uuid.uuid4().hex[:6]
PASSED: list[str] = []
FAILED: list[str] = []
STATE: dict[str, Any] = {}


def check(name: str, ok: bool, detail: Any = "") -> bool:
    print(("  ✅ " if ok else "  ❌ ") + name + (f" — {str(detail)[:200]}" if detail else ""))
    (PASSED if ok else FAILED).append(name)
    return ok


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

    def patch(self, url, **kw):
        return self.request("PATCH", url, **kw)

    def delete(self, url, **kw):
        return self.request("DELETE", url, **kw)


async def seed() -> None:
    from sqlalchemy import select

    from app import db, security
    from app.models import (
        Bot,
        Dialog,
        DialogChannel,
        DialogKind,
        Message,
        MessageDirection,
        MessageStatus,
        RelayLink,
        RelayRoute,
        RelayTargetKind,
        Task,
        TaskStatus,
        TaskType,
        TgAccount,
    )

    api = Api()
    api.token = api.post("/api/auth/login", json={"username": "admin", "password": "admin12345"}).json()["access_token"]

    group = api.post("/api/groups", json={"name": f"删除验证分组-{SUFFIX}"}).json()
    proxy = api.post(
        "/api/proxies",
        json={"name": f"删除验证代理-{SUFFIX}", "scheme": "socks5", "host": "127.0.0.1", "port": 1080},
    ).json()
    account = api.post("/api/accounts", json={"phone": f"+8613500{int(SUFFIX, 16) % 100000:05d}7", "remark": f"验证备注-{SUFFIX}"}).json()
    account_del = api.post("/api/accounts", json={"phone": f"+8613501{int(SUFFIX, 16) % 100000:05d}7", "remark": f"验证备注-删除用-{SUFFIX}"}).json()
    operator = api.post(
        "/api/users",
        json={"username": f"c3-op-{SUFFIX}", "password": "op-pass-1234", "role": "operator"},
    ).json()
    STATE.update(group=group["id"], proxy=proxy["id"], account=account["id"], account_del=account_del["id"], operator=operator["id"])

    # 失败任务 3 条（2 条属于 operator 看不到的号 + 1 条无账号）、已完成 1 条、Bot + 转发规则 + 转发记录
    async with db.SessionFactory() as session:
        now = datetime.now(tz=timezone.utc)
        bot = Bot(name=f"delete验证Bot-{SUFFIX}", token_enc=security.encrypt_secret("123456:TESTTOKEN"), webhook_secret="s" * 8)
        session.add(bot)
        await session.flush()
        route = RelayRoute(name=f"测试规则-{SUFFIX}", bot_id=bot.id, staff_chat_id=-100999, target_kind=RelayTargetKind.group)
        session.add(route)
        await session.flush()

        dialog = Dialog(
            channel=DialogChannel.user_account,
            kind=DialogKind.private,
            account_id=uuid.UUID(account["id"]),
            tg_chat_id=int(now.timestamp()) * 10 + 7,
            title=f"转发来源会话-{SUFFIX}",
            last_message_at=now,
        )
        session.add(dialog)
        await session.flush()
        message = Message(
            dialog_id=dialog.id,
            channel=DialogChannel.user_account,
            direction=MessageDirection.incoming,
            status=MessageStatus.received,
            body=f"转发来源消息-{SUFFIX}",
            sender_name="李四",
            created_at=now,
        )
        session.add(message)
        await session.flush()
        session.add(
            RelayLink(
                route_id=route.id, message_id=message.id, bot_id=bot.id,
                staff_chat_id=-100999, staff_message_id=555, created_at=now,
            )
        )

        failed_ids = []
        for _ in range(2):
            task = Task(
                type=TaskType.account_check, status=TaskStatus.failed, account_id=uuid.UUID(account["id"]),
                payload={}, attempts=5, max_attempts=5, error=f"验证用失败 {SUFFIX}",
                next_run_at=now, completed_at=now, created_at=now,
            )
            session.add(task)
            await session.flush()
            failed_ids.append(str(task.id))
        done = Task(
            type=TaskType.account_check, status=TaskStatus.completed, account_id=uuid.UUID(account["id"]),
            payload={}, attempts=1, completed_at=now, created_at=now,
        )
        session.add(done)
        await session.flush()
        STATE.update(route=str(route.id), bot=str(bot.id), dialog=str(dialog.id),
                     failed=failed_ids, done=str(done.id))
        await session.commit()
    api.client.close()
    await db.dispose_engine()


async def cleanup() -> None:
    from sqlalchemy import delete, select

    from app import db
    from app.models import AccountGroup, Bot, Proxy, RelayLink, RelayRoute, Task, TgAccount, User

    api = Api()
    login = api.post("/api/auth/login", json={"username": "admin", "password": "admin12345"})
    if login.status_code == 200:
        api.token = login.json()["access_token"]
        for key in ("account", "account_del"):
            if STATE.get(key):
                api.delete(f"/api/accounts/{STATE[key]}")
        if STATE.get("operator"):
            api.delete(f"/api/users/{STATE['operator']}")
        if STATE.get("proxy"):
            api.delete(f"/api/proxies/{STATE['proxy']}")
        if STATE.get("group"):
            api.delete(f"/api/groups/{STATE['group']}")
        if STATE.get("route"):
            api.delete(f"/api/relays/{STATE['route']}")
    api.client.close()

    async with db.SessionFactory() as session:
        await session.execute(delete(RelayLink).where(RelayLink.staff_message_id == 555))
        await session.execute(delete(RelayRoute).where(RelayRoute.name == f"测试规则-{SUFFIX}"))
        await session.execute(delete(Bot).where(Bot.name == f"delete验证Bot-{SUFFIX}"))
        await session.execute(delete(Task).where(Task.error == f"验证用失败 {SUFFIX}"))
        await session.execute(delete(AccountGroup).where(AccountGroup.name == f"删除验证分组-{SUFFIX}"))
        await session.execute(delete(Proxy).where(Proxy.name == f"删除验证代理-{SUFFIX}"))
        rows = list((await session.scalars(select(TgAccount).where(TgAccount.remark.like(f"验证备注-%{SUFFIX}")))).all())
        for row in rows:
            await session.delete(row)
        await session.commit()
    await db.dispose_engine()


def main() -> int:
    admin = Api()
    admin.token = admin.post("/api/auth/login", json={"username": "admin", "password": "admin12345"}).json()["access_token"]
    operator = Api()
    operator.token = operator.post(
        "/api/auth/login", json={"username": f"c3-op-{SUFFIX}", "password": "op-pass-1234"}
    ).json()["access_token"]

    print("A) 删除必须真的删掉（AsyncSession.delete 少了 await 的回归）")
    r = admin.delete(f"/api/groups/{STATE['group']}")
    check("DELETE 分组回 200", r.status_code == 200, r.json().get("message"))
    r = admin.get("/api/groups")
    check("分组真的没了", all(item["id"] != STATE["group"] for item in r.json()), [i["name"] for i in r.json()][:5])
    r = admin.delete(f"/api/proxies/{STATE['proxy']}")
    check("DELETE 代理回 200", r.status_code == 200, r.json().get("message"))
    r = admin.get("/api/proxies")
    check("代理真的没了", all(item["id"] != STATE["proxy"] for item in r.json()))
    r = admin.delete(f"/api/relays/{STATE['route']}")
    check("DELETE 转发规则回 200", r.status_code == 200, r.json().get("message"))
    r = admin.get("/api/relays")
    check("转发规则真的没了", all(item["id"] != STATE["route"] for item in r.json()))
    r = admin.delete(f"/api/accounts/{STATE['account_del']}")
    check("DELETE 账号回 200（原有行为没被破坏）", r.status_code == 200, r.json().get("message"))

    print("B) 审计时间范围 from/to")
    now = datetime.now(tz=timezone.utc)
    wide_from = (now - timedelta(hours=2)).isoformat()
    r = admin.get("/api/audit", params={"from": wide_from, "to": now.isoformat(), "page_size": 5})
    check("from/to 生效（近 2 小时有记录）", r.status_code == 200 and r.json().get("total", 0) >= 1, f"total={r.json().get('total')}")
    future = (now + timedelta(days=1)).isoformat()
    r = admin.get("/api/audit", params={"from": future})
    check("未来区间为空", r.status_code == 200 and r.json().get("total") == 0, f"total={r.json().get('total')}")
    r = admin.get("/api/audit", params={"from": now.isoformat(), "to": wide_from})
    check("from > to → 400 中文", r.status_code == 400 and "时间范围不合法" in r.json().get("detail", ""), r.json().get("detail"))
    r = admin.get("/api/audit", params={"from": (now - timedelta(hours=2)).replace(tzinfo=None).isoformat()})
    check("不带时区的 ISO8601 也能用（按 UTC）", r.status_code == 200, f"total={r.json().get('total')}")
    r = admin.get("/api/export/audit.csv", params={"from": wide_from, "to": now.isoformat()})
    text = r.content.decode("utf-8-sig")
    check("导出同步支持 from/to", r.status_code == 200 and len(text.splitlines()) >= 2, {"rows": len(text.splitlines()), "total": r.headers.get("x-export-total")})
    r = admin.get("/api/export/audit.csv", params={"from": future})
    check("导出未来区间只留表头", r.status_code == 200 and len(r.content.decode("utf-8-sig").splitlines()) == 1, r.headers.get("x-export-total"))

    print("C) 任务批量重试 POST /api/tasks/bulk/retry")
    failed = STATE["failed"]
    r = admin.post("/api/tasks/bulk/retry", json={"task_ids": failed + [str(uuid.uuid4()), STATE["done"], failed[0]]})
    body = r.json() if r.status_code == 200 else {}
    by_id = {item["task_id"]: item for item in body.get("results", [])}
    check(
        "批量重试：2 条成功 + 不存在/已完成/重复各一条 ok=false",
        r.status_code == 200 and body.get("requested") == 4 and body.get("succeeded") == 2 and body.get("failed") == 2,
        {k: body.get(k) for k in ("requested", "succeeded", "failed")},
    )
    check("不存在的任务记 ok:false 而不是报错", by_id.get(str(uuid.UUID(failed[0])) if False else [k for k in by_id][0], {}).get("ok") is not None)
    check("已完成任务 ok:false 且给中文原因", any(not i["ok"] and "不能重试" in i["message"] for i in body.get("results", [])), [i["message"] for i in body.get("results", []) if not i["ok"]][:2])
    check("重复 id 只处理一次（requested 去重后为 4）", body.get("requested") == 4, body.get("requested"))
    r = admin.get("/api/tasks", params={"status": "pending", "page_size": 200})
    pending_ids = {i["id"] for i in r.json().get("items", [])}
    check("重试后任务回到 pending 且 attempts 归零", all(fid in pending_ids for fid in failed), f"pending={len(pending_ids)}")
    r = admin.post("/api/tasks/bulk/retry", json={"task_ids": []})
    check("空 task_ids → 400 中文", r.status_code == 400 and "task_ids 不能为空" in r.json().get("detail", ""), r.json().get("detail"))
    r = admin.post("/api/tasks/bulk/retry", json={"task_ids": [str(uuid.uuid4()) for _ in range(201)]})
    check("超过 200 条 → 422", r.status_code == 422, f"HTTP {r.status_code}")
    r = operator.post("/api/tasks/bulk/retry", json={"task_ids": failed})
    body = r.json() if r.status_code == 200 else {}
    check(
        "operator 重试未分配号的任务 → 逐条 ok:false（不 500）",
        r.status_code == 200 and body.get("succeeded") == 0 and all("账号未分配给你" in i["message"] for i in body.get("results", [])),
        [i["message"] for i in body.get("results", [])],
    )
    r = admin.get("/api/audit", params={"action": "task.bulk_retry", "page_size": 3})
    check("批量重试写了审计（task.bulk_retry）", r.status_code == 200 and r.json().get("total", 0) >= 1, f"total={r.json().get('total')}")

    print("D) 转发测试消息 POST /api/relays/test")
    r = admin.post("/api/relays/test", json={"bot_id": str(uuid.uuid4()), "chat_id": -100123})
    check("Bot 不存在 → 400 中文", r.status_code == 400 and "Bot 不存在" in r.json().get("detail", ""), r.json().get("detail"))
    r = admin.post("/api/relays/test", json={"bot_id": STATE["bot"], "chat_id": -100123, "text": "测试"})
    check(
        "Token 是假的时候不是 500（400/409/502 都给中文）",
        r.status_code in (400, 409, 502) and any("\u4e00" <= c <= "\u9fff" for c in r.json().get("detail", "")),
        f"HTTP {r.status_code} {r.json().get('detail', '')[:90]}",
    )
    r = operator.post("/api/relays/test", json={"bot_id": STATE["bot"], "chat_id": -100123})
    check("operator 调测试转发 → 403（仅 admin）", r.status_code == 403, f"HTTP {r.status_code}")

    print("E) 转发记录补 origin_dialog_id")
    r = admin.get("/api/relays/links", params={"page_size": 5})
    items = r.json().get("items", []) if r.status_code == 200 else []
    target = [i for i in items if i.get("origin_dialog_id") == STATE["dialog"]]
    check(
        "RelayLinkOut 带 origin_dialog_id（能跳原会话）",
        bool(target) and target[0].get("origin_dialog_title") == f"转发来源会话-{SUFFIX}",
        target[0] if target else [i.get("origin_dialog_id") for i in items][:3],
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
        print("已清理第二轮测试数据")
    sys.exit(code)
