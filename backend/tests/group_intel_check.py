"""群情报验收（需先起栈）：无感采集的数据底座 + 查询与导出。

    cd backend && .venv/bin/python -m tests.group_intel_check

覆盖：群档案/成员/事件的写入与查询、概览统计、成员筛选、事件流过滤、CSV 导出、采集入队、权限隔离。
数据由脚本直写库模拟（真实采集由 Worker 的事件监听与采集任务完成）。
"""

from __future__ import annotations

import asyncio, os, pathlib, sys, uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

BACKEND = pathlib.Path("/Users/duannai/telegram云控/backend")
sys.path.insert(0, str(BACKEND)); os.chdir(BACKEND)
LOOP = asyncio.new_event_loop()
def run(c): return LOOP.run_until_complete(c)

BASE = "http://127.0.0.1:8000"; PASS: list[str] = []; FAIL: list[str] = []
SUF = uuid.uuid4().hex[:6]

def check(n, ok, d=""):
    (PASS if ok else FAIL).append(n); print(f"  {'OK' if ok else '!!'} {n} {str(d)[:110]}")

class Api:
    def __init__(s): s.c = httpx.Client(base_url=BASE, timeout=30); s.token = None
    def req(s, m, u, **kw):
        h = {"Authorization": f"Bearer {s.token}"} if s.token else {}
        return s.c.request(m, u, headers=h, **kw)
    def get(s, u, **kw): return s.req("GET", u, **kw)
    def post(s, u, **kw): return s.req("POST", u, **kw)

STATE: dict[str, Any] = {}

async def seed() -> None:
    """直写库造：一个账号 + 一个群档案 + 3 个成员 + 3 条事件（模拟监听/采集的产物）。"""
    from app import db, security
    from app.models import AccountStatus, Dialog, DialogChannel, DialogKind, GroupEvent, GroupMember, GroupProfile, TgAccount

    async with db.SessionFactory() as s:
        acc = TgAccount(phone_enc=security.encrypt_secret(f"+8613700{int(SUF,16)%100000:05d}"),
                        phone_hash=security.short_hash(f"+8613700{int(SUF,16)%100000:05d}"),
                        phone_masked="+8613****0000", display_name=f"情报号-{SUF}",
                        status=AccountStatus.healthy, import_source="session_string")
        s.add(acc); await s.flush()
        dialog = Dialog(channel=DialogChannel.user_account, kind=DialogKind.group, account_id=acc.id,
                        tg_chat_id=-(10**12 + int(SUF, 16) % 10**6), title=f"情报群-{SUF}", member_count=1234)
        s.add(dialog); await s.flush()
        profile = GroupProfile(account_id=acc.id, dialog_id=dialog.id, tg_chat_id=dialog.tg_chat_id,
                               title=dialog.title, username=f"intel_{SUF}", kind="megagroup", member_count=1234,
                               about="验收用群", is_public=True, source="join_event",
                               collected_at=datetime.now(tz=timezone.utc))
        s.add(profile); await s.flush()
        now = datetime.now(tz=timezone.utc)
        for i, (status, bot) in enumerate((("member", False), ("member", True), ("left", False))):
            s.add(GroupMember(group_id=profile.id, account_id=acc.id, tg_chat_id=dialog.tg_chat_id,
                              tg_user_id=999000 + i + int(SUF, 16) % 1000, username=f"u{i}_{SUF}",
                              display_name=f"成员{i}", is_bot=bot, status=status,
                              source="join_event" if i == 0 else "participant_sync", last_seen_at=now))
        for i, etype in enumerate(("join", "invite", "leave")):
            s.add(GroupEvent(account_id=acc.id, tg_chat_id=dialog.tg_chat_id, tg_user_id=999000 + i,
                             event_type=etype, actor_tg_id=555000 if etype == "invite" else None,
                             user_display=f"事件{i}", occurred_at=now - timedelta(minutes=i * 5), source="join_event"))
        await s.commit()
        STATE.update(account=acc.id, profile=profile.id, chat_id=dialog.tg_chat_id, group=dialog.title)

def main() -> None:
    run(seed())
    api = Api()
    api.token = api.post("/api/auth/login", json={"username": "admin", "password": "admin12345"}).json()["access_token"]

    r = api.get("/api/group-intel/stats")
    st = r.json()
    check("概览统计", r.status_code == 200 and st["groups"] >= 1 and st["members"] >= 3, st)

    r = api.get("/api/group-intel/profiles", params={"q": SUF, "page": 1, "page_size": 10})
    body = r.json()
    check("群档案列表与搜索", r.status_code == 200 and body["total"] == 1 and body["items"][0]["username"] == f"intel_{SUF}", body.get("total"))

    pid = body["items"][0]["id"]
    r = api.get(f"/api/group-intel/profiles/{pid}")
    check("群档案详情含统计", r.status_code == 200 and r.json()["members"]["counts"], r.json().get("members"))

    r = api.get(f"/api/group-intel/profiles/{pid}/members", params={"page": 1, "page_size": 20})
    check("成员名单", r.status_code == 200 and r.json()["total"] == 3, r.json().get("total"))
    r = api.get(f"/api/group-intel/profiles/{pid}/members", params={"exclude_bots": True})
    check("成员筛选（排除机器人）", r.json()["total"] == 2, r.json().get("total"))
    r = api.get(f"/api/group-intel/profiles/{pid}/members", params={"status": "left"})
    check("成员筛选（已退群）", r.json()["total"] == 1, r.json().get("total"))

    r = api.get("/api/group-intel/events", params={"tg_chat_id": STATE["chat_id"], "hours": 24})
    ev = r.json()
    check("事件流（按群）", r.status_code == 200 and ev["total"] == 3 and ev["items"][0]["event_type_label"], (ev.get("counts"), ev["items"][0]["group_title"] if ev["items"] else None))
    r = api.get("/api/group-intel/events", params={"event_type": "invite", "hours": 24})
    check("事件流（按类型）", r.json()["total"] >= 1 and all(i["event_type"] == "invite" for i in r.json()["items"]), r.json().get("total"))

    r = api.get("/api/group-intel/members.csv", params={"profile_id": pid})
    text = r.text
    check("成员 CSV 导出", r.status_code == 200 and "用户ID" in text and text.count("\n") >= 3, text.splitlines()[0][:60] if text else "")

    # 采集入队：该号已同步过这个群，应当排队 collect_group
    r = api.post("/api/group-intel/collect", json={"account_ids": [str(STATE["account"])], "limit_groups": 5, "sample_members": 10})
    check("采集任务入队", r.status_code == 200 and r.json()["succeeded"] == 1 and r.json()["task_ids"], r.json().get("message"))

    async def cleanup():
        from sqlalchemy import delete
        from app import db
        from app.models import Dialog, GroupEvent, GroupMember, GroupProfile, Task, TgAccount
        async with db.SessionFactory() as s:
            await s.execute(delete(GroupEvent).where(GroupEvent.tg_chat_id == STATE["chat_id"]))
            await s.execute(delete(GroupMember).where(GroupMember.tg_chat_id == STATE["chat_id"]))
            await s.execute(delete(GroupProfile).where(GroupProfile.tg_chat_id == STATE["chat_id"]))
            await s.execute(delete(Task).where(Task.account_id == STATE["account"]))
            await s.execute(delete(Dialog).where(Dialog.account_id == STATE["account"]))
            await s.execute(delete(TgAccount).where(TgAccount.id == STATE["account"]))
            await s.commit()
    run(cleanup())

    print(f"\n通过 {len(PASS)}，失败 {len(FAIL)}")
    for n in FAIL: print("  x", n)
    sys.exit(1 if FAIL else 0)

main()
