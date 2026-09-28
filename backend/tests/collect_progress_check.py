"""采集进度与打包导出验收（需先起栈）：

    cd backend && .venv/bin/python -m tests.collect_progress_check

覆盖：进度端点结构、任务阶段快照（模拟 Worker 写 result）、批次过滤、打包 zip 内容
（groups.csv / members/*.csv / events.csv / manifest.json）与行数一致性。
"""

from __future__ import annotations

import asyncio, io, json, os, pathlib, sys, uuid, zipfile
from datetime import datetime, timedelta, timezone

import httpx

sys.path.insert(0, "/Users/duannai/telegram云控/backend"); os.chdir("/Users/duannai/telegram云控/backend")
LOOP = asyncio.new_event_loop()
def run(c): return LOOP.run_until_complete(c)

BASE = "http://127.0.0.1:8000"; PASS = []; FAIL = []
SUF = uuid.uuid4().hex[:6]

def check(n, ok, d=""):
    (PASS if ok else FAIL).append(n); print(f"  {'OK' if ok else '!!'} {n} {str(d)[:110]}")

STATE = {}

async def seed():
    from app import db, security
    from app.models import AccountStatus, GroupEvent, GroupMember, GroupProfile, Task, TaskStatus, TaskType, TgAccount
    async with db.SessionFactory() as s:
        phone = f"+8613500{int(SUF, 16) % 100000:05d}"
        acc = TgAccount(phone_enc=security.encrypt_secret(phone), phone_hash=security.short_hash(phone),
                        phone_masked="+8613****0002", display_name=f"进度号-{SUF}", status=AccountStatus.healthy)
        s.add(acc); await s.flush()
        batch = str(uuid.uuid4())
        chat_id = -(10**12 + int(SUF, 16) % 10**6)
        now = datetime.now(tz=timezone.utc)
        profile = GroupProfile(account_id=acc.id, tg_chat_id=chat_id, title=f"打包群-{SUF}", username=f"zip_{SUF}",
                               kind="megagroup", member_count=88, about="打包验收", is_public=True,
                               collected_at=now, member_synced_at=now, member_sampled=2)
        s.add(profile); await s.flush()
        for i, bot in enumerate((False, True)):
            s.add(GroupMember(group_id=profile.id, account_id=acc.id, tg_chat_id=chat_id,
                              tg_user_id=888000 + i, username=f"m{i}_{SUF}", display_name=f"打包成员{i}",
                              is_bot=bot, status="member", source="participant_sync", last_seen_at=now))
        s.add(GroupEvent(account_id=acc.id, tg_chat_id=chat_id, tg_user_id=888000, event_type="join",
                         user_display="打包成员0", occurred_at=now, source="join_event"))
        # 造三条采集任务：一条完成（带阶段快照）、一条执行中、一条失败
        s.add(Task(type=TaskType.collect_link, status=TaskStatus.completed, account_id=acc.id,
                   payload={"link": "t.me/finished_group", "batch_id": batch, "member_limit": 100},
                   result={"stage": "done", "detail": "采集完成：完成群 共 2 人", "fetched": 2, "target_count": 100,
                           "title": f"打包群-{SUF}", "tg_chat_id": chat_id}, attempts=1))
        s.add(Task(type=TaskType.collect_link, status=TaskStatus.running, account_id=acc.id,
                   payload={"link": "t.me/running_group", "batch_id": batch, "member_limit": 500},
                   result={"stage": "fetching", "detail": "已采 120/500 人", "fetched": 120, "target_count": 500},
                   attempts=1))
        s.add(Task(type=TaskType.collect_link, status=TaskStatus.failed, account_id=acc.id,
                   payload={"link": "t.me/broken_group", "batch_id": batch, "member_limit": 200},
                   result=None, error="该号不在群里：勾选自动加入后可采集", attempts=2))
        await s.commit()
        STATE.update(account=acc.id, profile=profile.id, chat_id=chat_id, batch=batch)

def main():
    run(seed())
    c = httpx.Client(base_url=BASE, timeout=60)
    tok = c.post("/api/auth/login", json={"username": "admin", "password": "admin12345"}).json()["access_token"]
    H = {"Authorization": f"Bearer {tok}"}

    r = c.get("/api/group-intel/jobs", headers=H, params={"batch_id": STATE["batch"], "limit": 20})
    body = r.json()
    jobs = body.get("jobs", [])
    check("进度端点返回任务", r.status_code == 200 and len(jobs) == 3, len(jobs))
    by_link = {j.get("link"): j for j in jobs}
    check("完成任务的阶段快照", by_link.get("t.me/finished_group", {}).get("stage") == "done"
          and by_link["t.me/finished_group"]["fetched"] == 2, by_link.get("t.me/finished_group", {}).get("detail"))
    check("执行中任务的实时进度", by_link.get("t.me/running_group", {}).get("stage") == "fetching"
          and by_link["t.me/running_group"]["fetched"] == 120, by_link.get("t.me/running_group", {}).get("detail"))
    check("失败任务带原因", by_link.get("t.me/broken_group", {}).get("stage") == "failed"
          and "不在群里" in by_link["t.me/broken_group"]["error"], by_link.get("t.me/broken_group", {}).get("error"))
    s = body.get("summary", {})
    check("进度汇总", s.get("total") == 3 and s.get("completed") == 1 and s.get("failed") == 1 and s.get("active") == 1,
          s)

    r = c.get("/api/group-intel/jobs", headers=H, params={"only_active": True})
    check("只看进行中", all(j["status"] in ("pending", "running") for j in r.json()["jobs"]), len(r.json()["jobs"]))

    # 打包：按群打包
    r = c.get("/api/group-intel/export.zip", headers=H, params={"profile_ids": str(STATE["profile"])})
    check("打包返回 zip", r.status_code == 200 and r.headers.get("content-type", "").startswith("application/zip"), r.headers.get("content-type"))
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    check("zip 内含群总表/成员/事件/清单",
          any(n == "groups.csv" for n in names) and any(n.startswith("members/") for n in names)
          and "events.csv" in names and "manifest.json" in names, names)
    groups_csv = zf.read("groups.csv").decode("utf-8-sig")
    check("群总表含该群", f"打包群-{SUF}" in groups_csv and "群ID" in groups_csv, groups_csv.splitlines()[0][:50])
    member_file = [n for n in names if n.startswith("members/")][0]
    member_csv = zf.read(member_file).decode("utf-8-sig")
    check("成员明细行数正确", len([l for l in member_csv.splitlines() if l.strip()]) == 3, f"{member_file}: {len(member_csv.splitlines())} 行")
    manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
    check("清单统计一致", manifest["groups"] == 1 and manifest["members"] == 2 and manifest["events"] == 1, manifest)

    # 打包：按批次（该批任务的 result 里有 tg_chat_id）
    r = c.get("/api/group-intel/export.zip", headers=H, params={"batch_id": STATE["batch"]})
    check("按批次打包", r.status_code == 200 and len(zipfile.ZipFile(io.BytesIO(r.content)).namelist()) >= 3, r.status_code)

    # 打包：不存在的批次
    r = c.get("/api/group-intel/export.zip", headers=H, params={"batch_id": str(uuid.uuid4())})
    check("空批次给出 404", r.status_code == 404, r.status_code)

    async def cleanup():
        from sqlalchemy import delete
        from app import db
        from app.models import GroupEvent, GroupMember, GroupProfile, Task, TgAccount
        async with db.SessionFactory() as s:
            await s.execute(delete(GroupEvent).where(GroupEvent.tg_chat_id == STATE["chat_id"]))
            await s.execute(delete(GroupMember).where(GroupMember.tg_chat_id == STATE["chat_id"]))
            await s.execute(delete(GroupProfile).where(GroupProfile.tg_chat_id == STATE["chat_id"]))
            await s.execute(delete(Task).where(Task.account_id == STATE["account"]))
            await s.execute(delete(TgAccount).where(TgAccount.id == STATE["account"]))
            await s.commit()
    run(cleanup())

    print(f"\n通过 {len(PASS)}，失败 {len(FAIL)}")
    for n in FAIL: print("  x", n)
    sys.exit(1 if FAIL else 0)

main()
