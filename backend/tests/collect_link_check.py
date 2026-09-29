"""按链接采集验收：链接解析规则 + 任务入队 + 校验（需先起栈）。

    cd backend && .venv/bin/python -m tests.collect_link_check
"""
from __future__ import annotations
import asyncio, os, pathlib, sys, uuid
import httpx

LOOP = asyncio.new_event_loop()
def run(coro): return LOOP.run_until_complete(coro)
sys.path.insert(0, "/Users/duannai/telegram云控/backend"); os.chdir("/Users/duannai/telegram云控/backend")
BASE="http://127.0.0.1:8000"; PASS=[]; FAIL=[]
def check(n, ok, d=""):
    (PASS if ok else FAIL).append(n); print(f"  {'OK' if ok else '!!'} {n} {str(d)[:110]}")

c = httpx.Client(base_url=BASE, timeout=30)
tok = c.post("/api/auth/login", json={"username":"admin","password":"admin12345"}).json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}

# 建一个测试账号（带会话，便于任务入队后能被执行）
import asyncio, uuid as _uuid
from app import db, security
from app.models import AccountStatus, TgAccount
SUF = uuid.uuid4().hex[:6]
async def mk():
    async with db.SessionFactory() as s:
        phone=f"+113600{int(SUF,16)%100000:05d}"
        acc=TgAccount(phone_enc=security.encrypt_secret(phone), phone_hash=security.short_hash(phone),
                      phone_masked="+1138****0001", display_name=f"链接采集-{SUF}", status=AccountStatus.healthy,
                      session_enc=security.encrypt_secret("1BVtsOKfakeSessionForShape"), import_source="session_string")
        s.add(acc); await s.commit(); return acc.id
acc_id = run(mk())

# 1) 多种链接形态都能被接受并入队
links = ["https://t.me/some_public_group", "t.me/+AbCdEfGh1234", "@another_group", "-1001234567890"]
r = c.post("/api/group-intel/collect-link", headers=H,
           json={"account_ids":[str(acc_id)], "links": links, "join_if_missing": True, "leave_after": True, "member_limit": 50})
body = r.json()
check("四种链接形态入队", r.status_code==200 and body["succeeded"]==4 and len(body["task_ids"])==4, body.get("message"))
check("回执里逐条列出链接", all("已排队" in i["message"] for i in body["items"]), body["items"][0]["message"][:60])

# 2) 任务 payload 带 join/leave/limit
async def inspect():
    from sqlalchemy import select
    from app.models import Task
    async with db.SessionFactory() as s:
        rows=list((await s.scalars(select(Task).where(Task.id.in_([uuid.UUID(t) for t in body["task_ids"]])))).all())
        return [(r.type.value, r.payload.get("link"), r.payload.get("join_if_missing"), r.payload.get("leave_after"), r.payload.get("member_limit")) for r in rows]
info = run(inspect())
check("任务类型与 payload", all(i[0]=="collect_link" and i[2] is True and i[3] is True and i[4]==50 for i in info), info[0] if info else None)

# 3) 校验：空链接 / 超量 / 非法链接长度
r = c.post("/api/group-intel/collect-link", headers=H, json={"account_ids":[str(acc_id)], "links": ["   "]})
check("空链接 422", r.status_code==422, r.status_code)
r = c.post("/api/group-intel/collect-link", headers=H, json={"account_ids":[str(acc_id)], "links": [f"@g{i}" for i in range(51)]})
check("超过 50 个链接 422", r.status_code==422, r.status_code)
r = c.post("/api/group-intel/collect-link", headers=H, json={"account_ids":[str(acc_id)], "links": ["t.me/x","t.me/x"]})
check("重复链接自动去重", r.json().get("succeeded")==1, r.json().get("message"))

# 4) 多链接轮询分配账号（这里只有 1 个号，验证不报错即可）
r = c.post("/api/group-intel/collect-link", headers=H, json={"account_ids":[str(acc_id)], "links": ["t.me/a","t.me/b","t.me/c"]})
check("多链接批量入队", r.json().get("succeeded")==3, r.json().get("message"))

async def cleanup():
    from sqlalchemy import delete
    from app.models import Task, TgAccount
    async with db.SessionFactory() as s:
        await s.execute(delete(Task).where(Task.account_id==acc_id))
        await s.execute(delete(TgAccount).where(TgAccount.id==acc_id))
        await s.commit()
run(cleanup())

print(f"\n通过 {len(PASS)}，失败 {len(FAIL)}")
for n in FAIL: print("  x", n)
sys.exit(1 if FAIL else 0)
