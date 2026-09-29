"""素材与私信/群发联动验收：

    cd backend && .venv/bin/python -m tests.material_pm_check

覆盖：批量私信与群发接受 material_id、payload 透传、素材不存在时任务报错可读、
素材群发入口保持可用。
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
    async with db.SessionFactory() as s:
        phone = f"+1202555{int(SUF, 16) % 10000:04d}"
        acc = TgAccount(phone_enc=security.encrypt_secret(phone), phone_hash=security.short_hash(phone),
                        phone_masked="+1202****0001", display_name=f"素材联动-{SUF}", status=AccountStatus.healthy)
        s.add(acc); await s.flush(); await s.commit(); return acc.id

def main():
    acc_id = run(seed())
    c = httpx.Client(base_url=BASE, timeout=30)
    tok = c.post("/api/auth/login", json={"username": "admin", "password": "admin12345"}).json()["access_token"]
    H = {"Authorization": f"Bearer {tok}"}

    # 建一个文字素材
    mat = c.post("/api/materials", headers=H, json={"kind": "text", "name": f"联动-{SUF}", "text": "素材正文"})
    check("素材创建", mat.status_code in (200, 201), mat.status_code)
    mid = mat.json()["id"]

    # 批量私信带素材
    r = c.post("/api/campaigns/bulk-pm", headers=H, json={
        "scope": "selected", "account_ids": [str(acc_id)], "targets": ["@someone"],
        "texts": ["配文"], "material_id": mid,
    })
    body = r.json()
    check("批量私信接受 material_id", r.status_code == 200 and body["succeeded"] == 1, body.get("message"))

    async def inspect():
        from sqlalchemy import select
        from app import db
        from app.models import Task
        async with db.SessionFactory() as s:
            row = await s.scalar(select(Task).where(Task.id == uuid.UUID(body["task_ids"][0])))
            return row.payload.get("material_id"), row.payload.get("texts")
    passed = run(inspect())
    check("material_id 进 payload", passed[0] == mid, passed)

    # 群发带素材
    r = c.post("/api/campaigns/group-broadcast", headers=H, json={
        "scope": "selected", "account_ids": [str(acc_id)], "target_group": "@somegroup",
        "texts": ["配文"], "material_id": mid,
    })
    check("群发接受 material_id", r.status_code == 200 and r.json()["succeeded"] == 1, r.json().get("message"))

    # 不带素材仍然可用（兼容）
    r = c.post("/api/campaigns/bulk-pm", headers=H, json={
        "scope": "selected", "account_ids": [str(acc_id)], "targets": ["@someone"], "texts": ["纯文本"],
    })
    check("不带素材保持兼容", r.status_code == 200 and r.json()["succeeded"] == 1, r.json().get("message"))

    # 不存在的素材：接口 404
    r = c.post("/api/campaigns/bulk-pm", headers=H, json={
        "scope": "selected", "account_ids": [str(acc_id)], "targets": ["@x"],
        "texts": ["t"], "material_id": str(uuid.uuid4()),
    })
    check("不存在的素材被拦", r.status_code == 404, r.status_code)

    async def cleanup():
        from sqlalchemy import delete
        from app import db
        from app.models import Material, Task, TgAccount
        async with db.SessionFactory() as s:
            await s.execute(delete(Task).where(Task.account_id == acc_id))
            await s.execute(delete(Material).where(Material.name.like(f"%{SUF}%")))
            await s.execute(delete(TgAccount).where(TgAccount.id == acc_id))
            await s.commit()
    run(cleanup())
    print(f"\n通过 {len(PASS)}，失败 {len(FAIL)}")
    for n in FAIL: print("  x", n)
    sys.exit(1 if FAIL else 0)

main()
