#!/usr/bin/env python3
"""控制台新增接口验收（永久回归，需先起栈：./scripts/stack_local.sh up）：

    cd backend && .venv/bin/python -m tests.console_api

覆盖：批量操作 A / 导出 B / 详情聚合 C / 趋势 D / 通知 E / 排序搜索 F / 权限与边界。
自建测试数据（直接写库造失败任务、异常账号、会话消息），结束后清理。
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

# 脚本在 /tmp，需要把 backend 目录塞进 sys.path 并切到那里（.env 按 cwd 读）
BACKEND = pathlib.Path(os.environ.get("TGCC_BACKEND", "/Users/duannai/telegram云控/backend"))
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

BASE = "http://127.0.0.1:8000"
PASSED: list[str] = []
FAILED: list[str] = []
SUFFIX = uuid.uuid4().hex[:6]


def now() -> datetime:
    return datetime.now(tz=timezone.utc)


def check(name: str, ok: bool, detail: Any = "") -> bool:
    text = str(detail)[:220]
    if ok:
        PASSED.append(name)
        print(f"  ✅ {name}{(' — ' + text) if text else ''}")
    else:
        FAILED.append(name)
        print(f"  ❌ {name}{(' — ' + text) if text else ''}")
    return ok


class Api:
    def __init__(self, base: str = BASE, timeout: float = 30.0) -> None:
        self.client = httpx.Client(base_url=base, timeout=timeout)
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


# ---------------- 数据准备 / 清理（直接写库，仅测试用） ----------------

STATE: dict[str, Any] = {}


async def seed() -> None:
    from sqlalchemy import select, update

    from app import db
    from app.models import (
        AccountGroup,
        AccountStatus,
        Dialog,
        DialogChannel,
        DialogKind,
        Message,
        MessageDirection,
        MessageStatus,
        Proxy,
        Task,
        TaskStatus,
        TaskType,
        TgAccount,
    )
    from app.redis_client import close_redis, get_redis

    api = Api()
    r = api.post("/api/auth/login", json={"username": "admin", "password": "admin12345"})
    assert r.status_code == 200, r.text
    api.token = r.json()["access_token"]

    group = api.post("/api/groups", json={"name": f"验证分组-{SUFFIX}", "description": "console-check"}).json()
    proxy = api.post(
        "/api/proxies",
        json={"name": f"验证代理-{SUFFIX}", "scheme": "socks5", "host": "127.0.0.1", "port": 1080},
    ).json()

    accounts = []
    for i in (1, 2, 3):
        phone = f"+8613900{int(SUFFIX, 16) % 100000:05d}{i}"
        created = api.post(
            "/api/accounts",
            json={"phone": phone, "group_id": group["id"], "proxy_id": proxy["id"], "remark": f"验证备注-{SUFFIX}-{i}"},
        )
        assert created.status_code in (200, 201), created.text
        account_id = created.json()["id"]
        api.patch(f"/api/accounts/{account_id}", json={"display_name": f"验证号{SUFFIX}-{i}"})
        accounts.append(account_id)
    STATE.update(group=group["id"], proxy=proxy["id"], accounts=accounts)

    operator = api.post(
        "/api/users",
        json={"username": f"cc-op-{SUFFIX}", "password": "op-pass-1234", "display_name": "验证员工", "role": "operator"},
    ).json()
    STATE["operator"] = operator["id"]
    api.post("/api/assignments", json={"user_id": operator["id"], "account_ids": [accounts[0]]})
    api.client.close()

    # 造一条失败任务（给 acc1） + acc2 状态异常 + acc2 的会话与消息
    async with db.SessionFactory() as session:
        moment = now()
        task = Task(
            type=TaskType.account_check,
            status=TaskStatus.failed,
            account_id=uuid.UUID(accounts[0]),
            payload={},
            priority=100,
            attempts=5,
            max_attempts=5,
            error=f"验证用：故意失败的检测任务 {SUFFIX}",
            next_run_at=moment,
            completed_at=moment,
            created_at=moment,
        )
        session.add(task)
        await session.flush()
        STATE["task"] = str(task.id)

        await session.execute(
            update(TgAccount)
            .where(TgAccount.id == uuid.UUID(accounts[1]))
            .values(status=AccountStatus.frozen, status_reason=f"验证用：Telegram 限制 {SUFFIX}")
        )
        dialog = Dialog(
            channel=DialogChannel.user_account,
            kind=DialogKind.private,
            account_id=uuid.UUID(accounts[1]),
            tg_chat_id=int(moment.timestamp()) * 10 + 1,
            title=f"验证会话标题-{SUFFIX}",
            peer_display="张三",
            unread_count=2,
            last_message_at=moment,
            last_message_preview=f"预览：验证预览 {SUFFIX}",
        )
        session.add(dialog)
        await session.flush()
        session.add(
            Message(
                dialog_id=dialog.id,
                channel=DialogChannel.user_account,
                direction=MessageDirection.incoming,
                status=MessageStatus.received,
                body=f"验证关键词蓝色文件夹-{SUFFIX} 在会议室",
                sender_name="张三",
                created_at=moment,
            )
        )
        STATE["dialog"] = str(dialog.id)
        await session.commit()

    redis = get_redis()
    await redis.set(
        "tgcc:backup:last-result",
        json.dumps({"ok": False, "kind": "daily", "ts": moment.isoformat(), "message": f"验证用：pg_dump 退出码 1 {SUFFIX}"}),
        ex=900,
    )
    await close_redis()
    await db.dispose_engine()


async def cleanup() -> None:
    from sqlalchemy import delete, or_, select, update

    from app import db
    from app.models import Notification, Task
    from app.redis_client import close_redis, get_redis

    api = Api()
    r = api.post("/api/auth/login", json={"username": "admin", "password": "admin12345"})
    if r.status_code == 200:
        api.token = r.json()["access_token"]
        for account_id in STATE.get("accounts", []):
            api.delete(f"/api/accounts/{account_id}")
        for key in ("operator",):
            if STATE.get(key):
                api.delete(f"/api/users/{STATE[key]}")
        if STATE.get("proxy"):
            api.delete(f"/api/proxies/{STATE['proxy']}")
        if STATE.get("group"):
            api.delete(f"/api/groups/{STATE['group']}")
    api.client.close()

    async with db.SessionFactory() as session:
        # 全局类通知不随账号级联删除，按 dedupe_key 清掉测试产生的那条
        await session.execute(
            delete(Notification).where(Notification.dedupe_key.like("backup_failed:daily:%"))
        )
        await session.commit()

    redis = get_redis()
    await redis.delete("tgcc:backup:last-result")
    await close_redis()
    await db.dispose_engine()


async def set_frozen(account_id: str, suffix: str) -> None:
    """把某个号改成 frozen（验证账号异常通知用）。"""
    from sqlalchemy import update

    from app import db
    from app.models import AccountStatus, TgAccount

    async with db.SessionFactory() as session:
        await session.execute(
            update(TgAccount)
            .where(TgAccount.id == uuid.UUID(account_id))
            .values(status=AccountStatus.frozen, status_reason=f"验证用：Telegram 限制 {suffix}")
        )
        await session.commit()
    await db.dispose_engine()


async def clear_notify_gate() -> None:
    """清掉通知聚合的 20 秒节流键，让下一次 GET 立刻重新聚合。"""
    from app.redis_client import close_redis, get_redis

    redis = get_redis()
    await redis.delete("tgcc:notifications:last-sync")
    await close_redis()


# ---------------- 各组验收 ----------------

def main() -> int:
    admin = Api()
    r = admin.post("/api/auth/login", json={"username": "admin", "password": "admin12345"})
    if r.status_code != 200:
        print("管理员登录失败：", r.text)
        return 1
    admin.token = r.json()["access_token"]

    acc1, acc2, acc3 = STATE["accounts"]
    operator = Api()
    r = operator.post("/api/auth/login", json={"username": f"cc-op-{SUFFIX}", "password": "op-pass-1234"})
    check("operator 登录", r.status_code == 200, r.text[:120])
    operator.token = r.json().get("access_token")

    # ---------- A. 批量操作 ----------
    print("A) 批量账号操作")
    r = admin.post("/api/accounts/bulk/check", json={"account_ids": [acc1, acc2]})
    body = r.json() if r.status_code == 200 else {}
    check(
        "bulk/check 两个号",
        r.status_code == 200 and body.get("requested") == 2 and body.get("succeeded") == 2 and len(body.get("task_ids", [])) == 2,
        {k: body.get(k) for k in ("requested", "succeeded", "failed", "truncated")},
    )
    check(
        "bulk/check item 带 reachable/status_label",
        bool(body.get("items")) and "reachable" in body["items"][0] and body["items"][0].get("status_label") != "",
        body.get("items", [{}])[0],
    )
    r = admin.post("/api/accounts/bulk/sync-dialogs", json={"scope": f"group:{STATE['group']}"})
    body = r.json() if r.status_code == 200 else {}
    check(
        "bulk/sync-dialogs 按分组",
        r.status_code == 200 and body.get("requested") == 3 and len(body.get("task_ids", [])) == 3,
        body.get("message"),
    )
    r = admin.post("/api/accounts/bulk/check", json={"scope": "all", "limit": 1})
    check(
        "limit 截断有提示",
        r.status_code == 200 and r.json().get("truncated") is True and r.json().get("requested") == 1,
        {k: r.json().get(k) for k in ("requested", "truncated")},
    )
    r = admin.post("/api/accounts/bulk/check", json={"scope": "bogus"})
    check("非法 scope → 400 中文", r.status_code == 400 and "scope" in r.json().get("detail", ""), r.json().get("detail"))
    r = admin.post("/api/accounts/bulk/check", json={"account_ids": [str(uuid.uuid4())]})
    check("不存在的账号 → 404", r.status_code == 404 and "账号不存在" in r.json().get("detail", ""), r.json().get("detail"))
    r = admin.post("/api/accounts/bulk/check")
    check("批量端点允许不带 body（等价 {} → 提示没选中）", r.status_code == 400 and "没有选中任何账号" in r.json().get("detail", ""), r.json().get("detail"))
    r = admin.post("/api/accounts/bulk/release-lease", json={})
    check("空 body 的 release-lease 也是 400 而不是 500", r.status_code == 400, r.json().get("detail"))

    r = admin.post("/api/accounts/bulk/status", json={"account_ids": [acc1, acc2], "enabled": False})
    check(
        "bulk/status 停用",
        r.status_code == 200 and r.json().get("succeeded") == 2,
        r.json().get("message"),
    )
    r = admin.get(f"/api/accounts/{acc1}")
    check("停用后状态是 disabled", r.json().get("status") == "disabled", r.json().get("status"))
    r = admin.post("/api/accounts/bulk/enable", json={"account_ids": [acc1, acc2]})
    check("bulk/enable 别名", r.status_code == 200 and r.json().get("action") == "enable", r.json().get("message"))
    r = admin.get(f"/api/accounts/{acc1}")
    check("无会话的号启用后回 pending", r.json().get("status") == "pending", r.json().get("status"))

    r = admin.post("/api/accounts/bulk/group", json={"account_ids": [acc1], "group_id": None})
    check("bulk/group 移出分组", r.status_code == 200 and admin.get(f"/api/accounts/{acc1}").json()["group_id"] is None, r.json().get("message"))
    r = admin.post("/api/accounts/bulk/group", json={"account_ids": [acc1], "group_id": STATE["group"]})
    check("bulk/group 归组", r.status_code == 200 and admin.get(f"/api/accounts/{acc1}").json()["group_id"] == STATE["group"])
    r = admin.post("/api/accounts/bulk/group", json={"account_ids": [acc1], "group_id": str(uuid.uuid4())})
    check("分组不存在 → 400 中文", r.status_code == 400 and r.json().get("detail") == "分组不存在", r.json().get("detail"))

    r = admin.post("/api/accounts/bulk/proxy", json={"account_ids": [acc1], "proxy_id": None})
    check("bulk/proxy 改直连", r.status_code == 200 and admin.get(f"/api/accounts/{acc1}").json()["proxy_id"] is None)
    r = admin.post("/api/accounts/bulk/proxy", json={"account_ids": [acc1], "proxy_id": STATE["proxy"]})
    check("bulk/proxy 绑代理", r.status_code == 200 and admin.get(f"/api/accounts/{acc1}").json()["proxy_id"] == STATE["proxy"])
    r = admin.post("/api/accounts/bulk/proxy", json={"account_ids": [acc1], "proxy_id": str(uuid.uuid4())})
    check("代理不存在 → 400 中文", r.status_code == 400 and r.json().get("detail") == "代理不存在")

    r = admin.post("/api/accounts/bulk/release-lease", json={"scope": "all"})
    check("bulk/release-lease", r.status_code == 200 and r.json().get("succeeded", 0) >= 1, r.json().get("message"))

    r = admin.post("/api/accounts/bulk/assign", json={"user_id": STATE["operator"], "account_ids": [acc3], "mode": "assign"})
    check("bulk/assign 分配", r.status_code == 200 and r.json().get("succeeded") == 1, r.json().get("message"))
    r = admin.post("/api/accounts/bulk/assign", json={"user_id": STATE["operator"], "account_ids": [acc3], "mode": "unassign"})
    check("bulk/assign 取消分配", r.status_code == 200 and r.json().get("action") == "unassign", r.json().get("message"))
    r = admin.post("/api/accounts/bulk/assign", json={"user_id": STATE["operator"], "account_ids": [acc3], "mode": "wat"})
    check("非法 mode → 400", r.status_code == 400 and "mode" in r.json().get("detail", ""), r.json().get("detail"))

    if operator.token:
        r = operator.post("/api/accounts/bulk/check", json={"account_ids": [acc1, acc2]})
        check("operator 批量检测未分配号 → 403", r.status_code == 403, f"HTTP {r.status_code}")
        r = operator.post("/api/accounts/bulk/check", json={"account_ids": [acc1]})
        check("operator 批量检测自己号 → 200", r.status_code == 200, r.json().get("message"))
        r = operator.post("/api/accounts/bulk/status", json={"scope": "all", "enabled": False})
        check(
            "operator scope=all 收敛为分配范围",
            r.status_code == 200 and r.json().get("requested") == 1,
            {k: r.json().get(k) for k in ("requested", "succeeded")},
        )
        r = operator.post("/api/accounts/bulk/assign", json={"user_id": STATE["operator"], "account_ids": [acc1]})
        check("operator 用批量分配 → 403（仅 admin）", r.status_code == 403, r.json().get("detail"))

    spec = httpx.get(f"{BASE}/openapi.json", timeout=20).json()
    bulk_paths = [p for p in spec["paths"] if "/bulk/" in p]
    forbidden_words = ("send", "message", "join", "leave", "invite", "broadcast", "mass", "profile", "spam")
    check(
        "批量端点里没有发送/群发/加群/退群/改资料",
        not [p for p in bulk_paths if any(w in p for w in forbidden_words)],
        sorted(bulk_paths),
    )

    # ---------- C. 账号详情聚合 ----------
    print("C) 账号详情聚合")
    r = admin.get(f"/api/accounts/{acc1}/overview")
    body = r.json() if r.status_code == 200 else {}
    check(
        "overview 返回抽屉所需字段",
        r.status_code == 200
        and {"account", "group", "proxy", "lease", "dialog_stats", "task_stats", "recent_dialogs", "recent_messages", "recent_tasks", "recent_audit", "generated_at"} <= set(body),
        sorted(body)[:12],
    )
    check("overview 任务统计含失败数", body.get("task_stats", {}).get("failed", 0) >= 1, body.get("task_stats"))
    check("overview 最近审计非空（操作都留痕）", len(body.get("recent_audit", [])) >= 1, len(body.get("recent_audit", [])))
    check("overview 账号是脱敏手机号", "****" in body.get("account", {}).get("phone_masked", ""), body.get("account", {}).get("phone_masked"))
    r = admin.get(f"/api/accounts/{acc2}/overview")
    check(
        "overview 带会话统计",
        r.status_code == 200 and r.json()["dialog_stats"]["total"] >= 1 and r.json()["dialog_stats"]["unread"] >= 1,
        r.json().get("dialog_stats"),
    )
    r = admin.get(f"/api/accounts/{uuid.uuid4()}/overview")
    check("overview 不存在 → 404", r.status_code == 404 and r.json().get("detail") == "账号不存在", r.json().get("detail"))
    if operator.token:
        r = operator.get(f"/api/accounts/{acc1}/overview")
        check("operator 看自己号的 overview → 200", r.status_code == 200)
        r = operator.get(f"/api/accounts/{acc2}/overview")
        check("operator 看未分配号的 overview → 403", r.status_code == 403, r.json().get("detail"))

    # ---------- F. 列表排序与搜索 ----------
    print("F) 排序 / 搜索")
    r = admin.get("/api/accounts", params={"keyword": SUFFIX, "sort": "display_name", "order": "asc", "page_size": 50})
    names = [i["display_name"] for i in r.json().get("items", [])]
    check("accounts sort=display_name&order=asc 生效", r.status_code == 200 and names == sorted(names), names)
    r = admin.get("/api/accounts", params={"keyword": SUFFIX, "sort": "display_name", "order": "desc", "page_size": 50})
    names_desc = [i["display_name"] for i in r.json().get("items", [])]
    check("accounts order=desc 生效", names_desc == sorted(names_desc, reverse=True), names_desc)
    r = admin.get("/api/accounts", params={"sort": "drop table"})
    check("非法排序字段 → 400 中文", r.status_code == 400 and "不支持的排序字段" in r.json().get("detail", ""), r.json().get("detail"))
    r = admin.get("/api/accounts", params={"order": "sideways"})
    check("非法 order → 400 中文", r.status_code == 400 and "order 只能是" in r.json().get("detail", ""), r.json().get("detail"))
    r = admin.get("/api/accounts", params={"page_size": 1000})
    check("page_size 超上限 → 422", r.status_code == 422, f"HTTP {r.status_code}")

    r = admin.get("/api/dialogs", params={"q": f"蓝色文件夹-{SUFFIX}"})
    check(
        "dialogs q 命中消息正文",
        r.status_code == 200 and any(i["id"] == STATE["dialog"] for i in r.json().get("items", [])),
        f"total={r.json().get('total')}",
    )
    r = admin.get("/api/dialogs", params={"q": f"验证会话标题-{SUFFIX}"})
    check("dialogs q 命中标题", r.status_code == 200 and r.json().get("total", 0) >= 1, f"total={r.json().get('total')}")
    r = admin.get("/api/dialogs", params={"sort": "unread_count", "order": "desc"})
    check("dialogs 支持 sort/order", r.status_code == 200, f"total={r.json().get('total')}")
    r = admin.get("/api/messages", params={"q": f"蓝色文件夹-{SUFFIX}"})
    body = r.json() if r.status_code == 200 else {}
    check(
        "GET /api/messages q 搜索正文",
        r.status_code == 200 and body.get("total", 0) >= 1 and body["items"][0]["body"].find(SUFFIX) >= 0,
        {k: body.get(k) for k in ("total", "page", "page_size")},
    )
    r = admin.get("/api/messages", params={"dialog_id": STATE["dialog"], "sort": "created_at", "order": "asc"})
    check("GET /api/messages 支持 sort/order + dialog_id", r.status_code == 200 and r.json().get("total", 0) >= 1)
    r = admin.get(f"/api/dialogs/{STATE['dialog']}/messages", params={"q": f"蓝色文件夹-{SUFFIX}"})
    check("会话内消息 q 搜索", r.status_code == 200 and len(r.json().get("items", [])) == 1, f"total={r.json().get('total')}")
    r = admin.get("/api/tasks", params={"sort": "priority", "order": "asc"})
    check("tasks 支持 sort/order", r.status_code == 200)
    r = admin.get("/api/audit", params={"sort": "action", "order": "asc"})
    check("audit 支持 sort/order", r.status_code == 200)
    if operator.token:
        r = operator.get("/api/messages", params={"q": f"蓝色文件夹-{SUFFIX}"})
        check("operator 搜不到未分配号的消息", r.status_code == 200 and r.json().get("total") == 0, f"total={r.json().get('total')}")
        r = operator.get("/api/messages", params={"dialog_id": STATE["dialog"]})
        check("operator 按未分配会话搜 → 403", r.status_code == 403, f"HTTP {r.status_code}")
        r = operator.get("/api/dialogs", params={"q": f"蓝色文件夹-{SUFFIX}"})
        check("operator 会话搜索不含未分配会话", r.status_code == 200 and r.json().get("total") == 0)

    # ---------- B. CSV 导出 ----------
    print("B) CSV 导出")
    r = admin.get("/api/export/accounts.csv", params={"keyword": SUFFIX})
    raw = r.content
    check(
        "accounts.csv 头正确（BOM + text/csv + 附件名）",
        r.status_code == 200
        and raw[:3] == b"\xef\xbb\xbf"
        and r.headers["content-type"].startswith("text/csv")
        and f'filename="accounts_' in r.headers.get("content-disposition", ""),
        {k: v for k, v in r.headers.items() if k.lower() in ("content-type", "content-disposition", "x-export-total", "x-export-truncated")},
    )
    text = raw.decode("utf-8-sig")
    check(
        "accounts.csv 中文（表头 + 备注）不乱码",
        "手机号(脱敏)" in text and f"验证备注-{SUFFIX}-1" in text,
        text.splitlines()[0][:80],
    )
    check("accounts.csv 行数含筛选（3 行数据）", len([l for l in text.splitlines() if l.strip()]) == 4, len(text.splitlines()))
    check("X-Export-Total 与行数一致", r.headers.get("x-export-total") == "3", r.headers.get("x-export-total"))
    r2 = admin.get("/api/export/accounts.csv", params={"keyword": SUFFIX, "sort": "display_name", "order": "asc"})
    rows = [line for line in r2.content.decode("utf-8-sig").splitlines()[1:] if line.strip()]
    check("导出支持 sort/order", rows and "验证号" + SUFFIX + "-1" in rows[0], rows[0][:60] if rows else "")

    r = admin.get("/api/export/tasks.csv", params={"status": "failed"})
    text = r.content.decode("utf-8-sig")
    check(
        "tasks.csv 含失败原因（中文）",
        r.status_code == 200 and f"故意失败的检测任务 {SUFFIX}" in text and "账号检测" in text and "失败" in text,
        [line[:90] for line in text.splitlines() if SUFFIX in line][:1] or text.splitlines()[:2],
    )
    r = admin.get("/api/export/audit.csv")
    text = r.content.decode("utf-8-sig")
    check(
        "audit.csv 有导出记录（谁导了什么）",
        r.status_code == 200 and "导出 CSV" in text and "export.download" in text,
        r.headers.get("x-export-total"),
    )
    r = admin.get("/api/export/dialogs.csv", params={"q": f"蓝色文件夹-{SUFFIX}"})
    check(
        "dialogs.csv 支持 q（跨正文）",
        r.status_code == 200 and f"验证会话标题-{SUFFIX}" in r.content.decode("utf-8-sig"),
        r.headers.get("x-export-total"),
    )
    r = admin.get("/api/export/messages.csv", params={"q": f"蓝色文件夹-{SUFFIX}"})
    text = r.content.decode("utf-8-sig")
    check(
        "messages.csv 导出正文",
        r.status_code == 200 and f"蓝色文件夹-{SUFFIX}" in text and "正文" in text,
        r.headers.get("x-export-total"),
    )
    r = admin.get("/api/export/messages.csv", params={"dialog_id": str(uuid.uuid4())})
    check("导出不存在会话的消息 → 404", r.status_code == 404, r.json().get("detail"))
    r = admin.get("/api/export/accounts.csv", params={"sort": "nope"})
    check("导出非法排序字段 → 400", r.status_code == 400, r.json().get("detail"))
    if operator.token:
        r = operator.get("/api/export/accounts.csv")
        check(
            "operator 导出只含分配到的号",
            r.status_code == 200 and r.headers.get("x-export-total") == "1",
            r.headers.get("x-export-total"),
        )
        r = operator.get("/api/export/messages.csv", params={"dialog_id": STATE["dialog"]})
        check("operator 导出未分配会话消息 → 403", r.status_code == 403, f"HTTP {r.status_code}")

    # ---------- E. 通知 ----------
    print("E) 通知流")
    # 前面的批量停用/启用把 acc2 的状态改掉了，这里重新造一个「异常账号」再触发聚合
    asyncio.run(set_frozen(acc2, SUFFIX))
    asyncio.run(clear_notify_gate())
    r = admin.get("/api/notifications", params={"page_size": 50})
    body = r.json() if r.status_code == 200 else {}
    kinds = {i["kind"] for i in body.get("items", [])}
    check(
        "通知聚合出四类来源（本次至少任务失败/账号异常/备份失败）",
        r.status_code == 200 and {"task_failed", "account_abnormal", "backup_failed"} <= kinds,
        sorted(kinds),
    )
    check(
        "通知带中文 kind_label / level / link",
        all(i.get("kind_label") and i.get("level") in ("info", "warning", "error", "success") for i in body.get("items", [])),
        {i["kind"]: i["level"] for i in body.get("items", [])},
    )
    check("counts_by_kind 有四个键", set(body.get("counts_by_kind", {})) == {"task_failed", "worker_lost", "account_abnormal", "backup_failed"}, body.get("counts_by_kind"))
    check("unread 计数可用", body.get("unread", 0) >= 1, body.get("unread"))
    task_notifications = [i for i in body.get("items", []) if i["kind"] == "task_failed"]
    check(
        "失败任务通知带账号脱敏号与中文标题",
        bool(task_notifications) and "****" in (task_notifications[0].get("account_label") or "") and "任务失败" in task_notifications[0]["title"],
        task_notifications[0]["title"] if task_notifications else "",
    )
    r = admin.get("/api/notifications", params={"kind": "task_failed", "page_size": 50})
    check("按 kind 过滤", r.status_code == 200 and all(i["kind"] == "task_failed" for i in r.json()["items"]), f"total={r.json().get('total')}")
    r = admin.get("/api/notifications", params={"unread_only": True, "page_size": 50})
    check("unread_only 只回未读", r.status_code == 200 and all(i["read"] is False for i in r.json()["items"]), f"total={r.json().get('total')}")
    r = admin.get("/api/notifications", params={"kind": "", "level": ""})
    check("空 kind/level 参数按不筛选处理", r.status_code == 200, f"total={r.json().get('total')}")
    r = admin.get("/api/notifications", params={"kind": "nope"})
    check("非法 kind → 400 中文", r.status_code == 400 and "kind 只能是" in r.json().get("detail", ""), r.json().get("detail"))
    r = admin.get("/api/notifications", params={"level": "nope"})
    check("非法 level → 400 中文", r.status_code == 400 and "level 只能是" in r.json().get("detail", ""), r.json().get("detail"))
    r = admin.get("/api/notifications", params={"sort": "created_at", "order": "asc", "page_size": 5})
    check("通知支持 sort/order", r.status_code == 200 and len(r.json().get("items", [])) <= 5)

    if task_notifications:
        nid = task_notifications[0]["id"]
        r = admin.post(f"/api/notifications/{nid}/read")
        check(
            "标记已读返回 read=true",
            r.status_code == 200 and r.json()["notification"]["read"] is True and r.json()["notification"].get("read_at"),
            r.json().get("message"),
        )
        r = admin.post(f"/api/notifications/{nid}/read")
        check("重复标记已读幂等", r.status_code == 200 and "本来就已经读过" in r.json().get("message", ""), r.json().get("message"))
    r = admin.post(f"/api/notifications/{uuid.uuid4()}/read")
    check("读不存在的通知 → 404", r.status_code == 404 and r.json().get("detail") == "通知不存在")

    if operator.token:
        r = operator.get("/api/notifications", params={"page_size": 50})
        items = r.json().get("items", []) if r.status_code == 200 else []
        visible_account_ids = {i["account_id"] for i in items if i["account_id"]}
        check(
            "operator 只看到自己号 + 全局通知",
            r.status_code == 200 and (not visible_account_ids or visible_account_ids == {acc1}),
            {"accounts": sorted(x for x in visible_account_ids if x)},
        )
        check(
            "operator 看不到未分配号的异常通知",
            all(i["account_id"] != acc2 for i in items),
            f"items={len(items)}",
        )
        admin_items = admin.get("/api/notifications", params={"kind": "account_abnormal", "page_size": 50}).json().get("items", [])
        foreign = [i for i in admin_items if i["account_id"] == acc2]
        if foreign:
            r = operator.post(f"/api/notifications/{foreign[0]['id']}/read")
            check("operator 读未分配号的异常通知 → 403", r.status_code == 403, r.json().get("detail"))
        else:
            check("operator 读未分配号的异常通知 → 403", False, "没造出 acc2 的异常通知")
        r = operator.post("/api/notifications/read-all")
        check("operator read-all 只影响可见范围", r.status_code == 200 and r.json().get("marked", 0) >= 0, r.json().get("message"))

    r = admin.post("/api/notifications/read-all")
    check("admin read-all", r.status_code == 200, r.json().get("message"))
    r = admin.get("/api/notifications", params={"unread_only": True})
    check("read-all 后未读归零", r.json().get("unread") == 0 or r.json().get("total") == 0, {"unread": r.json().get("unread"), "total": r.json().get("total")})

    # ---------- D. 趋势 ----------
    print("D) 趋势")
    r = admin.get("/api/metrics/trends", params={"window": "24h"})
    body = r.json() if r.status_code == 200 else {}
    check(
        "trends?window=24h 形状正确",
        r.status_code == 200
        and body.get("granularity") == "hour"
        and {s["key"] for s in body.get("series", [])} == {"online_accounts", "abnormal_accounts", "tasks_succeeded", "tasks_failed"},
        {"granularity": body.get("granularity"), "points": len(body.get("points", []))},
    )
    check(
        "trends 有采样点（采样协程已写库）",
        bool(body.get("points")) and body.get("latest_sample_at") is not None,
        {"points": len(body.get("points", [])), "latest_sample_at": body.get("latest_sample_at")},
    )
    point = (body.get("points") or [{}])[0]
    series_point = body["series"][0]["points"][0] if body.get("series", [{}])[0].get("points") else {}
    check(
        "series 与 points 数值一致",
        series_point.get("v") == point.get("online_accounts") and series_point.get("t") == point.get("bucket"),
        {"series": series_point, "points": point},
    )
    check("trends from/to 字段存在（别名）", body.get("from") is not None and body.get("to") is not None, {"from": body.get("from"), "to": body.get("to")})
    r = admin.get("/api/metrics/trends", params={"range": "7d"})
    check("range=7d 逐天", r.status_code == 200 and r.json().get("granularity") == "day", r.json().get("granularity"))
    r = admin.get("/api/metrics/trends", params={"window": "30d"})
    check("window=30d 可用", r.status_code == 200 and r.json().get("granularity") == "day")
    r = admin.get("/api/metrics/trends", params={"window": "1y"})
    check("非法 window → 400 中文", r.status_code == 400 and "window 只能是" in r.json().get("detail", ""), r.json().get("detail"))
    if operator.token:
        r = operator.get("/api/metrics/trends", params={"window": "24h"})
        check("operator 也能看趋势（全局口径，仅计数）", r.status_code == 200, f"HTTP {r.status_code}")

    # ---------- 鉴权 ----------
    print("G) 未授权一律 401")
    for name, method, url, kwargs in (
        ("导出", "GET", "/api/export/accounts.csv", {}),
        ("通知", "GET", "/api/notifications", {}),
        ("趋势", "GET", "/api/metrics/trends", {}),
        ("批量检测", "POST", "/api/accounts/bulk/check", {"json": {"scope": "all"}}),
        ("概览", "GET", f"/api/accounts/{acc1}/overview", {}),
        ("消息搜索", "GET", "/api/messages", {}),
    ):
        r = httpx.request(method, f"{BASE}{url}", timeout=20, **kwargs)
        check(f"无 token 访问{name} → 401", r.status_code == 401, f"HTTP {r.status_code}")

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
        try:
            asyncio.run(cleanup())
            print("已清理测试数据")
        except Exception as exc:  # noqa: BLE001
            print("清理失败：", exc)
    sys.exit(code)
