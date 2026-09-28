"""官方机制养号验收（需先起栈）：

    cd backend && .venv/bin/python -m tests.official_check

覆盖：官方客户端身份表、服务端参数提取与「只收紧不放松」换算、批量养号入队、
官方参数同步入队、matrix 接口回传官方字段、任务类型白名单。
"""

from __future__ import annotations

import asyncio, os, pathlib, sys, uuid
from datetime import datetime, timedelta, timezone

import httpx

sys.path.insert(0, "/Users/duannai/telegram云控/backend"); os.chdir("/Users/duannai/telegram云控/backend")
LOOP = asyncio.new_event_loop()
def run(c): return LOOP.run_until_complete(c)

BASE = "http://127.0.0.1:8000"; PASS = []; FAIL = []
SUF = uuid.uuid4().hex[:6]

def check(n, ok, d=""):
    (PASS if ok else FAIL).append(n); print(f"  {'OK' if ok else '!!'} {n} {str(d)[:110]}")

# ---------------- 纯函数：官方参数解析与换算 ----------------
def pure_checks():
    from app.services.official import (
        OFFICIAL_CLIENTS, derive_throttle_overrides, extract_official_limits, pick_official_client,
    )
    check("官方客户端身份表非空且平台齐全",
          len(OFFICIAL_CLIENTS) >= 10 and {c.lang_pack for c in OFFICIAL_CLIENTS} >= {"android", "ios", "tdesktop"},
          sorted({c.lang_pack for c in OFFICIAL_CLIENTS}))
    picked = pick_official_client(prefer="ios")
    check("按平台挑选身份", picked.lang_pack == "ios", picked)

    # 服务端下发形态：Telethon 的 JsonObject，这里用等价 dict 模拟
    fake = type("Cfg", (), {"config": {"flood_wait": 90, "flood_add_peer": 30, "channels_read_media_period": 7,
                                       "upload_max_fileparts": 8000, "unrelated_flag": True}})()
    limits = extract_official_limits(fake)
    check("只提取限速相关键",
          set(limits) == {"flood_wait", "flood_add_peer"},
          limits)

    overrides = derive_throttle_overrides({"flood_wait": 90, "flood_add_peer": 30}, base_daily=200, base_interval=20)
    check("flood_wait 抬升最小间隔", overrides.get("min_action_seconds") == 90, overrides)
    check("flood_add_peer 限住加人类日额", overrides.get("add_peer_daily") == 30, overrides)
    # 官方参数比我们宽松时不能给我们松绑
    loose = derive_throttle_overrides({"flood_wait": 5}, base_daily=200, base_interval=60)
    check("只收紧不放松", loose.get("min_action_seconds") == 60, loose)

    # 节流实际生效（40 天老号：默认间隔 20 → 官方要求 90 时取 90）
    from app.models import TgAccount
    from app.services.throttle import daily_limit_for, min_interval_for, official_overrides
    acc = TgAccount(phone_masked="t", warmup_started_at=datetime.now(tz=timezone.utc) - timedelta(days=40),
                    official_limits={"flood_wait": 90})
    check("节流按官方参数收紧", min_interval_for(acc) == 90, f"间隔={min_interval_for(acc)}")
    check("覆盖值可查询", official_overrides(acc).get("min_action_seconds") == 90, official_overrides(acc))
    check("每日额度不超默认上限", daily_limit_for(acc) == 200, daily_limit_for(acc))

# ---------------- 接口：批量养号入队与官方字段 ----------------
async def seed():
    from app import db, security
    from app.models import AccountStatus, TgAccount
    async with db.SessionFactory() as s:
        phone = f"+8613400{int(SUF, 16) % 100000:05d}"
        acc = TgAccount(phone_enc=security.encrypt_secret(phone), phone_hash=security.short_hash(phone),
                        phone_masked="+8613****0003", display_name=f"养号-{SUF}", status=AccountStatus.healthy,
                        client_kind="android", official_limits={"flood_wait": 45, "flood_add_peer": 25},
                        official_synced_at=datetime.now(tz=timezone.utc))
        s.add(acc); await s.commit(); return acc.id

def api_checks(acc_id):
    c = httpx.Client(base_url=BASE, timeout=30)
    tok = c.post("/api/auth/login", json={"username": "admin", "password": "admin12345"}).json()["access_token"]
    H = {"Authorization": f"Bearer {tok}"}

    r = c.post("/api/accounts/bulk/warmup", headers=H, json={
        "account_ids": [str(acc_id)], "rounds": 2, "online_min_seconds": 30, "online_max_seconds": 60,
        "sync_limits": True,
    })
    body = r.json()
    check("批量养号入队", r.status_code == 200 and body["succeeded"] == 1 and len(body["task_ids"]) == 2,
          body.get("message"))

    async def inspect():
        from sqlalchemy import select
        from app import db
        from app.models import Task
        async with db.SessionFactory() as s:
            rows = list((await s.scalars(
                select(Task).where(Task.id.in_([uuid.UUID(t) for t in body["task_ids"]]))
            )).all())
            return sorted([(row.type.value, (row.payload or {}).get("rounds"), (row.payload or {}).get("source")) for row in rows])
    info = run(inspect())
    check("两条任务类型正确", [i[0] for i in info] == ["sync_official", "warmup_activity"], info)

    r = c.get(f"/api/accounts/{acc_id}/matrix", headers=H)
    m = r.json()
    check("matrix 回传官方身份", r.status_code == 200 and m.get("client_kind") == "android", m.get("client_kind"))
    check("matrix 回传官方参数", m.get("official_limits", {}).get("flood_wait") == 45, m.get("official_limits"))
    # 新号阶梯间隔是 120 秒，官方要求 45 秒——取更严的 120，这才是「只收紧不放松」
    ov = m.get("official_overrides", {})
    check("换算后取更严的间隔", ov.get("min_action_seconds") == max(120, 45), ov)
    check("加人类日额受官方限制", ov.get("add_peer_daily") == 25, ov)
    check("节流快照含官方同步时间", bool(m.get("throttle", {}).get("official_synced_at")), m.get("throttle", {}).get("official_synced_at"))

    # 白名单：官方任务可批量重试
    import pathlib as _p
    src = (_p.Path("/Users/duannai/telegram云控/backend/app/api/routers/tasks.py")).read_text(encoding="utf-8")
    check("官方任务纳入批量重试白名单", "TaskType.sync_official" in src and "TaskType.warmup_activity" in src, "")

    async def cleanup():
        from sqlalchemy import delete
        from app import db
        from app.models import Task, TgAccount
        async with db.SessionFactory() as s:
            await s.execute(delete(Task).where(Task.account_id == acc_id))
            await s.execute(delete(TgAccount).where(TgAccount.id == acc_id))
            await s.commit()
    run(cleanup())

def main():
    pure_checks()
    api_checks(run(seed()))
    print(f"\n通过 {len(PASS)}，失败 {len(FAIL)}")
    for n in FAIL: print("  x", n)
    sys.exit(1 if FAIL else 0)

main()
