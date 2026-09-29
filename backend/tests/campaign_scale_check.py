"""营销中心规模化验收：手动选号（部分账号）+ 目标轮询分发 + 并发配置。

    cd backend && .venv/bin/python -m tests.campaign_scale_check

覆盖：scope=selected 只对指定号建任务、dispatch=round_robin 把目标按账号轮流切分、
each 模式每个号拿全量目标、dispatch 进入 payload、部分账号与全量的账号数差异。
"""

from __future__ import annotations

import asyncio, os, pathlib, sys, uuid

import httpx

sys.path.insert(0, "/Users/duannai/telegram云控/backend"); os.chdir("/Users/duannai/telegram云控/backend")
LOOP = asyncio.new_event_loop()
def run(c): return LOOP.run_until_complete(c)

BASE = "http://127.0.0.1:8000"; PASS = []; FAIL = []
SUF = uuid.uuid4().hex[:6]

def check(n, ok, d=""):
    (PASS if ok else FAIL).append(n); print(f"  {'OK' if ok else '!!'} {n} {str(d)[:110]}")

async def seed():
    from app import db, security
    from app.models import AccountStatus, TgAccount
    ids = []
    async with db.SessionFactory() as s:
        for i in range(4):
            phone = f"+1202555{int(SUF, 16) % 10000:04d}{i}"
            acc = TgAccount(phone_enc=security.encrypt_secret(phone), phone_hash=security.short_hash(phone),
                            phone_masked=f"+1202****{i:04d}", display_name=f"规模化-{SUF}-{i}",
                            status=AccountStatus.healthy)
            s.add(acc); await s.flush(); ids.append(acc.id)
        await s.commit()
    return ids

def main():
    ids = run(seed())
    c = httpx.Client(base_url=BASE, timeout=30)
    tok = c.post("/api/auth/login", json={"username": "admin", "password": "admin12345"}).json()["access_token"]
    H = {"Authorization": f"Bearer {tok}"}
    targets = [f"@t{i}" for i in range(5)]

    # 1) 手动选号（部分账号）：只挑前两个号
    r = c.post("/api/campaigns/bulk-pm", headers=H, json={
        "scope": "selected", "account_ids": [str(ids[0]), str(ids[1])],
        "targets": targets, "texts": ["你好"], "dispatch": "round_robin",
    })
    body = r.json()
    check("手动选号只对指定账号建任务", r.status_code == 200 and body["succeeded"] == 2, body.get("message"))
    task_ids = body.get("task_ids", [])

    async def inspect():
        from sqlalchemy import select
        from app import db
        from app.models import Task
        async with db.SessionFactory() as s:
            rows = list((await s.scalars(select(Task).where(Task.id.in_([uuid.UUID(t) for t in task_ids])))).all())
            return [(str(row.account_id), row.payload.get("targets"), row.payload.get("dispatch"),
                     row.payload.get("account_index"), row.payload.get("account_count")) for row in rows]
    info = run(inspect())
    check("dispatch 写入 payload", all(i[2] == "round_robin" for i in info), [i[2] for i in info])
    check("账号总数正确", all(i[4] == 2 for i in info), [i[4] for i in info])
    sliced = {i[3]: i[1] for i in info}
    check("轮询切分：两个号各自拿到一半目标", len(sliced) == 2 and sorted(sum(sliced.values(), [])) == sorted(targets),
          sliced)
    check("切分互不重叠", set(sliced.get(0, [])) & set(sliced.get(1, [])) == set(), sliced)

    # 2) each 模式：每个号都拿全量目标
    r = c.post("/api/campaigns/bulk-pm", headers=H, json={
        "scope": "selected", "account_ids": [str(ids[0]), str(ids[1])],
        "targets": targets, "texts": ["你好"], "dispatch": "each",
    })
    task_ids2 = r.json()["task_ids"]

    async def inspect2():
        from sqlalchemy import select
        from app import db
        from app.models import Task
        async with db.SessionFactory() as s:
            rows = list((await s.scalars(select(Task).where(Task.id.in_([uuid.UUID(t) for t in task_ids2])))).all())
            return [row.payload.get("targets") for row in rows]
    got = run(inspect2())
    check("each 模式每个号拿全量目标", all(len(t or []) == 5 for t in got), [len(t or []) for t in got])

    # 3) 素材群发轮询（需要素材）
    mat = c.post("/api/materials", headers=H, json={"kind": "text", "name": f"规模化素材-{SUF}", "text": "素材内容"})
    if mat.status_code in (200, 201):
        mid = mat.json()["id"]
        r = c.post("/api/campaigns/material-send", headers=H, json={
            "scope": "selected", "account_ids": [str(ids[2]), str(ids[3])],
            "material_id": mid, "targets": targets, "dispatch": "round_robin",
        })
        check("素材群发支持轮询分发", r.status_code == 200 and r.json()["succeeded"] == 2, r.json().get("message"))

    # 3.5) 批量加群：多群 + 轮询切分
    r = c.post("/api/campaigns/join-group", headers=H, json={
        "scope": "selected", "account_ids": [str(ids[0]), str(ids[1])],
        "targets": ["t.me/+aaa", "@g1", "@g2", "@g3"], "dispatch": "round_robin",
    })
    check("批量加群接受多群", r.status_code == 200 and r.json()["succeeded"] == 2, r.json().get("message"))
    jt = r.json().get("task_ids", [])

    async def inspect_join():
        from sqlalchemy import select
        from app import db
        from app.models import Task
        async with db.SessionFactory() as s:
            rows = list((await s.scalars(select(Task).where(Task.id.in_([uuid.UUID(x) for x in jt])))).all())
            return {row.payload.get("account_index"): row.payload.get("targets") for row in rows}
    js = run(inspect_join())
    check("加群轮询切分不重叠", set(js.get(0, [])) & set(js.get(1, [])) == set() and len(sum(js.values(), [])) == 4, js)

    r = c.post("/api/campaigns/join-group", headers=H, json={
        "scope": "selected", "account_ids": [str(ids[0])], "target": "@legacy_single",
    })
    check("单个 target 保持兼容", r.status_code == 200 and r.json()["succeeded"] == 1, r.json().get("message"))

    r = c.post("/api/campaigns/join-group", headers=H, json={"scope": "all", "targets": []})
    check("空目标被拦", r.status_code == 422, r.status_code)

    # 4) 并发配置存在
    from app.config import settings
    check("并发可配且默认提升", settings.task_concurrency >= 10 and settings.task_batch >= 10,
          f"concurrency={settings.task_concurrency} batch={settings.task_batch}")

    async def cleanup():
        from sqlalchemy import delete
        from app import db
        from app.models import Material, Task, TgAccount
        async with db.SessionFactory() as s:
            await s.execute(delete(Task).where(Task.account_id.in_(ids)))
            await s.execute(delete(Material).where(Material.name.like(f"%{SUF}%")))
            await s.execute(delete(TgAccount).where(TgAccount.id.in_(ids)))
            await s.commit()
    run(cleanup())

    print(f"\n通过 {len(PASS)}，失败 {len(FAIL)}")
    for n in FAIL: print("  x", n)
    sys.exit(1 if FAIL else 0)

main()
