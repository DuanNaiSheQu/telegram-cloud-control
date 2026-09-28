#!/usr/bin/env python3
"""营销中心验收（永久回归，需先起栈：./scripts/stack_local.sh up）：

    cd backend && .venv/bin/python -m tests.campaign_api

覆盖：素材库 A / 九类批量动作入队 B / 请求校验 C / 批次聚合与取消 D /
operator 范围收敛 E / 批量重试白名单 F / 落库 payload 与错峰 G。
Worker 未配 TELEGRAM_API_ID 时任务停在 pending 是预期（只验入队与队列语义）。
"""

from __future__ import annotations

import asyncio
import io
import os
import pathlib
import sys
import uuid
from typing import Any, Optional

import httpx

BACKEND = pathlib.Path(os.environ.get("TGCC_BACKEND", "/Users/duannai/telegram云控/backend"))
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

# 全程共用一个事件循环：SQLAlchemy async engine 与 loop 绑定，反复 asyncio.run 会报 loop closed
_LOOP = asyncio.new_event_loop()


def run(coro: Any) -> Any:
    return _LOOP.run_until_complete(coro)


BASE = "http://127.0.0.1:8000"
PASSED: list[str] = []
FAILED: list[str] = []
SUFFIX = uuid.uuid4().hex[:6]
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360000000020001"
)


def check(name: str, ok: bool, detail: Any = "") -> bool:
    text = str(detail)[:200]
    (PASSED if ok else FAILED).append(name)
    print(f"  {'✅' if ok else '❌'} {name}{(' — ' + text) if text else ''}")
    return ok


class Api:
    def __init__(self, base: str = BASE) -> None:
        self.client = httpx.Client(base_url=base, timeout=30.0)
        self.token: Optional[str] = None

    def _headers(self, extra: Optional[dict] = None) -> dict:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        headers.update(extra or {})
        return headers

    def request(self, method: str, url: str, **kw) -> httpx.Response:
        headers = self._headers(dict(kw.pop("headers", {}) or {}))
        return self.client.request(method, url, headers=headers, **kw)

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def post(self, url, **kw):
        return self.request("POST", url, **kw)

    def delete(self, url, **kw):
        return self.request("DELETE", url, **kw)


STATE: dict[str, Any] = {}


def part_a(api: Api) -> None:
    r = api.post("/api/materials", json={"name": f"文字素材-{SUFFIX}", "kind": "text", "text": "验收文本"})
    check("A1 新建文字素材", r.status_code in (200, 201) and r.json().get("kind_label") == "文字", r.text[:100])
    STATE["material_text"] = r.json()["id"]

    files = {"file": ("sample.png", io.BytesIO(PNG_BYTES), "image/png")}
    r = api.post(f"/api/materials/upload?name=img-{SUFFIX}&caption=看图", files=files)
    body = r.json()
    check("A2 上传媒体素材", r.status_code in (200, 201) and body.get("kind") == "photo", r.text[:100])
    STATE["material_photo"] = body["id"]

    r = api.get("/api/materials", params={"page": 1, "page_size": 20})
    check("A3 素材列表含新素材", any(i["id"] == STATE["material_photo"] for i in r.json()["items"]), r.json().get("total"))

    r = api.get(f"/api/materials/{STATE['material_photo']}", params={"download": True})
    check("A4 媒体下载", r.status_code == 200 and r.content == PNG_BYTES, r.status_code)

    r = api.delete(f"/api/materials/{STATE['material_text']}")
    check("A5 删除文字素材", r.status_code == 200 and r.json().get("ok"), r.text[:80])


def part_b(api: Api, group_id: str) -> None:
    scope = {"scope": f"group:{group_id}", "account_ids": None, "limit": 10}
    r = api.post("/api/campaigns/bulk-pm", json={**scope, "targets": ["@durov", "+8613800000000"], "texts": ["你好", "在吗"], "min_interval": 2, "max_interval": 4})
    check("B1 批量私信入队", r.status_code == 200 and r.json()["succeeded"] == 3, r.text[:150])
    STATE["batch_pm"] = r.json()["task_ids"]

    r = api.post("/api/campaigns/group-broadcast", json={**scope, "target_group": "@somegroup", "text": "群发文案"})
    check("B2 群发入队", r.status_code == 200 and r.json()["succeeded"] == 3, r.text[:120])
    r = api.post("/api/campaigns/material-send", json={**scope, "material_id": STATE["material_photo"], "targets": ["@durov"]})
    check("B3 素材群发入队", r.status_code == 200 and r.json()["succeeded"] == 3, r.text[:120])
    r = api.post("/api/campaigns/join-group", json={**scope, "target": "https://t.me/+AbCdEfGh123456"})
    check("B4 加群入队", r.status_code == 200 and r.json()["succeeded"] == 3, r.text[:120])
    r = api.post("/api/campaigns/leave-group", json={**scope, "target": "@somegroup", "delete_history": True})
    check("B5 退群入队", r.status_code == 200 and r.json()["succeeded"] == 3, r.text[:120])
    r = api.post("/api/campaigns/force-add", json={**scope, "group": "@somegroup", "members": ["@user1", "@user2"]})
    check("B6 强拉入队", r.status_code == 200 and r.json()["succeeded"] == 3, r.text[:120])
    r = api.post("/api/campaigns/profile-update", json={**scope, "profile": {"first_name": "统一名字", "bio": "统一简介"}})
    check("B7 批量改资料入队", r.status_code == 200 and r.json()["succeeded"] == 3, r.text[:120])
    r = api.post("/api/campaigns/storm", json={**scope, "group": "@somegroup", "rounds": 5, "min_interval": 3, "max_interval": 20, "texts": ["顶", "看看"], "reply_probability": 0.3})
    check("B8 吵群入队", r.status_code == 200 and r.json()["succeeded"] == 3, r.text[:120])
    r = api.post("/api/campaigns/persona", json={**scope, "group": "@somegroup", "persona": "数码爱好者，爱用短句", "topic": "手机", "use_ai": False, "texts": ["确实"], "rounds": 3, "min_interval": 3, "max_interval": 10})
    check("B9 拟人发言入队", r.status_code == 200 and r.json()["succeeded"] == 3, r.text[:120])

    r = api.post("/api/campaigns/storm", json={**scope, "group": "@g", "rounds": 21, "texts": ["x"]})
    check("C1 吵群轮数超限 422", r.status_code == 422, r.status_code)
    r = api.post("/api/campaigns/bulk-pm", json={**scope, "targets": [], "text": "x"})
    check("C2 私信无目标 422", r.status_code == 422, r.status_code)
    r = api.post("/api/campaigns/persona", json={**scope, "group": "@g", "persona": "p", "rounds": 20, "min_interval": 50, "max_interval": 100})
    check("C3 拟人总时长超限 422", r.status_code == 422, r.status_code)
    r = api.post("/api/campaigns/force-add", json={**scope, "group": "@g", "members": [f"@u{i}" for i in range(51)]})
    check("C4 强拉成员超 50 个 422", r.status_code == 422, r.status_code)
    r = api.post("/api/campaigns/material-send", json={**scope, "material_id": str(uuid.uuid4()), "targets": ["@durov"]})
    check("C5 素材不存在 404", r.status_code == 404, r.status_code)


def part_d(api: Api) -> None:
    r = api.get("/api/campaigns/batches", params={"page": 1, "page_size": 50})
    check("D1 批次列表有数据", r.status_code == 200 and r.json()["total"] >= 9, r.json().get("total"))

    async def _batch_id() -> Optional[str]:
        from sqlalchemy import select

        from app import db
        from app.models import Task

        async with db.SessionFactory() as session:
            row = await session.scalar(select(Task).where(Task.id == uuid.UUID(STATE["batch_pm"][0])))
            return row.payload.get("batch_id") if row else None

    batch_id = run(_batch_id())
    check("D2 任务 payload 带 batch_id", bool(batch_id), batch_id)
    r = api.get(f"/api/campaigns/batches/{batch_id}")
    check("D3 批次详情逐号状态", r.status_code == 200 and r.json()["total"] == 3, r.json().get("total"))
    counts = r.json().get("counts", {})
    check("D4 批次状态计数", counts.get("pending", 0) + counts.get("running", 0) == 3, counts)
    r = api.post(f"/api/campaigns/batches/{batch_id}/cancel")
    check("D5 取消批次", r.status_code == 200 and r.json()["succeeded"] == 3, r.text[:120])


def part_e(api: Api) -> None:
    r = api.post("/api/users", json={"username": f"camp-op-{SUFFIX}", "password": "op-pass-1234", "display_name": "营销员工", "role": "operator"})
    op_uid = r.json()["id"]
    STATE.setdefault("operators", []).append(op_uid)
    api.post("/api/assignments", json={"user_id": op_uid, "account_ids": [STATE["accounts"][0]]})

    op = Api()
    op.token = op.post("/api/auth/login", json={"username": f"camp-op-{SUFFIX}", "password": "op-pass-1234"}).json()["access_token"]
    r = op.post("/api/campaigns/bulk-pm", json={"scope": "all", "limit": 50, "targets": ["@durov"], "text": "x"})
    check("E1 operator 的 all 收敛为分配给他的号", r.status_code == 200 and r.json()["succeeded"] == 1, r.text[:120])
    check("E2 提交返回审计动作名", r.json().get("action") == "campaign.bulk_pm", r.json().get("action"))


def part_f(api: Api) -> None:
    task_ids = STATE["batch_pm"]

    async def _fail() -> None:
        from sqlalchemy import update

        from app import db
        from app.models import Task, TaskStatus

        async with db.SessionFactory() as session:
            await session.execute(update(Task).where(Task.id.in_([uuid.UUID(i) for i in task_ids])).values(status=TaskStatus.failed))
            await session.commit()

    run(_fail())
    r = api.post("/api/tasks/bulk/retry", json={"task_ids": task_ids})
    body = r.json()
    check("F1 营销任务允许批量重试", r.status_code == 200 and body["succeeded"] == len(task_ids), body.get("results"))


def part_g() -> None:
    async def _inspect() -> dict:
        from sqlalchemy import select

        from app import db
        from app.models import Task

        async with db.SessionFactory() as session:
            rows = list((await session.scalars(select(Task).where(Task.id.in_([uuid.UUID(i) for i in STATE["batch_pm"]])))).all())
            rows.sort(key=lambda row: row.next_run_at)
            return {
                "count": len(rows),
                "staggered": all(rows[i].next_run_at < rows[i + 1].next_run_at for i in range(len(rows) - 1)) if len(rows) > 1 else False,
                "types": {row.type.value for row in rows},
                "payload_keys": sorted(rows[0].payload.keys()) if rows else [],
            }

    info = run(_inspect())
    check("G1 一 号一任务 + 类型正确", info["count"] == 3 and info["types"] == {"bulk_pm"}, info)
    check("G2 相邻号首发错峰", info["staggered"], info.get("staggered"))
    check("G3 payload 含 batch/account_index/目标", {"batch_id", "account_index", "account_count", "targets", "texts"} <= set(info["payload_keys"]), info["payload_keys"])


async def seed(api: Api) -> None:
    r = api.post("/api/auth/login", json={"username": "admin", "password": "admin12345"})
    assert r.status_code == 200, r.text
    api.token = r.json()["access_token"]
    group = api.post("/api/groups", json={"name": f"营销分组-{SUFFIX}", "description": "campaign-check"}).json()
    STATE["group"] = group["id"]
    accounts = []
    for i in (1, 2, 3):
        phone = f"+8613810{int(SUFFIX, 16) % 100000:05d}{i}"
        created = api.post("/api/accounts", json={"phone": phone, "group_id": group["id"], "remark": f"营销验收-{SUFFIX}-{i}"})
        assert created.status_code in (200, 201), created.text
        accounts.append(created.json()["id"])
    STATE["accounts"] = accounts


async def cleanup() -> None:
    from sqlalchemy import delete, select

    from app import db
    from app.models import AccountGroup, Material, TgAccount, User

    async with db.SessionFactory() as session:
        for account_id in STATE.get("accounts", []):
            row = await session.scalar(select(TgAccount).where(TgAccount.id == uuid.UUID(account_id)))
            if row is not None:
                await session.delete(row)
        if STATE.get("group"):
            row = await session.scalar(select(AccountGroup).where(AccountGroup.id == uuid.UUID(STATE["group"])))
            if row is not None:
                await session.delete(row)
        for operator_id in STATE.get("operators", []):
            row = await session.scalar(select(User).where(User.id == uuid.UUID(operator_id)))
            if row is not None:
                await session.delete(row)
        ids = [STATE.get(k) for k in ("material_photo", "material_text") if STATE.get(k)]
        await session.execute(delete(Material).where(Material.id.in_([uuid.UUID(i) for i in ids])))
        await session.commit()


def main() -> None:
    api = Api()
    run(seed(api))
    try:
        part_a(api)
        part_b(api, STATE["group"])
        part_d(api)
        part_e(api)
        part_f(api)
        part_g()
    finally:
        run(cleanup())

    print(f"\n通过 {len(PASSED)}，失败 {len(FAILED)}")
    for name in FAILED:
        print(f"  ✗ {name}")
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
