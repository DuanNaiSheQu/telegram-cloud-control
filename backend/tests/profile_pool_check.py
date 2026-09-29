"""批量改资料池化验收：

    cd backend && .venv/bin/python -m tests.profile_pool_check

覆盖：多行候选池进 payload、统一单值仍可用、用户名前缀+随机数字、
池化取值方式（sequence/random）、没有可改字段时报 400。
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
        for i in range(3):
            phone = f"+1202555{int(SUF, 16) % 10000:04d}{i}"
            acc = TgAccount(phone_enc=security.encrypt_secret(phone), phone_hash=security.short_hash(phone),
                            phone_masked=f"+1202****{i:04d}", display_name=f"池化-{SUF}-{i}", status=AccountStatus.healthy)
            s.add(acc); await s.flush(); ids.append(acc.id)
        await s.commit()
    return ids

def main():
    ids = run(seed())
    c = httpx.Client(base_url=BASE, timeout=30)
    tok = c.post("/api/auth/login", json={"username": "admin", "password": "admin12345"}).json()["access_token"]
    H = {"Authorization": f"Bearer {tok}"}

    # 1) 候选池 + 顺序分配 + 用户名前缀
    r = c.post("/api/campaigns/profile-update", headers=H, json={
        "scope": "selected", "account_ids": [str(i) for i in ids],
        "profile": {}, "first_name_pool": ["David", "Alex", "小林"],
        "bio_pool": ["做外贸的", "喜欢摄影", "周末爬山"],
        "assign_mode": "sequence", "username_prefix": f"u{SUF[:4]}_", "username_random_digits": 4,
    })
    body = r.json()
    check("池化改资料入队", r.status_code == 200 and body["succeeded"] == 3, body.get("message"))

    async def inspect():
        from sqlalchemy import select
        from app import db
        from app.models import Task
        async with db.SessionFactory() as s:
            rows = list((await s.scalars(select(Task).where(Task.id.in_([uuid.UUID(t) for t in body["task_ids"]])))).all())
            return [(row.payload.get("first_name_pool"), row.payload.get("assign_mode"),
                     row.payload.get("username_prefix"), row.payload.get("account_index")) for row in rows]
    info = run(inspect())
    check("候选池进 payload", all(i[0] == ["David", "Alex", "小林"] for i in info), info[0][0] if info else None)
    check("分配方式进 payload", all(i[1] == "sequence" for i in info), [i[1] for i in info])
    check("用户名前缀进 payload", all(i[2] and i[2].startswith("u") for i in info), [i[2] for i in info])
    check("账号序号连续（顺序分配的依据）", sorted(i[3] for i in info) == [0, 1, 2], [i[3] for i in info])

    # 2) 统一单值（兼容旧用法）
    r = c.post("/api/campaigns/profile-update", headers=H, json={
        "scope": "selected", "account_ids": [str(ids[0])],
        "profile": {"first_name": "统一名", "bio": "统一简介"},
    })
    check("统一单值保持兼容", r.status_code == 200 and r.json()["succeeded"] == 1, r.json().get("message"))

    # 3) 随机模式
    r = c.post("/api/campaigns/profile-update", headers=H, json={
        "scope": "selected", "account_ids": [str(ids[0])],
        "profile": {}, "last_name_pool": ["Chen", "Wang"], "assign_mode": "random",
    })
    check("随机模式可用", r.status_code == 200 and r.json()["succeeded"] == 1, r.json().get("message"))

    # 4) 什么都没填 → 400
    r = c.post("/api/campaigns/profile-update", headers=H, json={
        "scope": "selected", "account_ids": [str(ids[0])], "profile": {}, "assign_mode": "sequence",
    })
    check("没有可改字段报 400", r.status_code == 400, r.status_code)

    async def cleanup():
        from sqlalchemy import delete
        from app import db
        from app.models import Task, TgAccount
        async with db.SessionFactory() as s:
            await s.execute(delete(Task).where(Task.account_id.in_(ids)))
            await s.execute(delete(TgAccount).where(TgAccount.id.in_(ids)))
            await s.commit()
    run(cleanup())
    print(f"\n通过 {len(PASS)}，失败 {len(FAIL)}")
    for n in FAIL: print("  x", n)
    sys.exit(1 if FAIL else 0)

main()
