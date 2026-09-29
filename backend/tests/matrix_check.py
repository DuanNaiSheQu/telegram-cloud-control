"""账号矩阵验收（需先起栈 ./scripts/stack_local.sh up）：

    cd backend && .venv/bin/python -m tests.matrix_check

覆盖：导入方式枚举 / 手机号清单解析与落库 / 重复去重 / 非法 session 拦截 /
非 SQLite 文件错误 / 批量节流 / 深度验活入队 / 账号出参矩阵字段 / 矩阵状态接口 / 批次列表。
"""

import asyncio, io, os, pathlib, sys, uuid, httpx
BACKEND = pathlib.Path("/Users/duannai/telegram云控/backend"); sys.path.insert(0, str(BACKEND)); os.chdir(BACKEND)
LOOP = asyncio.new_event_loop()
def run(c): return LOOP.run_until_complete(c)
BASE="http://127.0.0.1:8000"; PASS=[]; FAIL=[]
def check(n, ok, d=""): (PASS if ok else FAIL).append(n); print(f"  {'OK' if ok else '!!'} {n} {str(d)[:120]}")
SUF=uuid.uuid4().hex[:6]

class Api:
    def __init__(s): s.c=httpx.Client(base_url=BASE, timeout=30); s.token=None
    def req(s, m, u, **kw):
        h={"Authorization": f"Bearer {s.token}"} if s.token else {}
        return s.c.request(m,u,headers=h,**kw)
    def get(s,u,**kw): return s.req("GET",u,**kw)
    def post(s,u,**kw): return s.req("POST",u,**kw)

async def seed(api):
    r=api.post("/api/auth/login", json={"username":"admin","password":"admin12345"}); assert r.status_code==200, r.text
    api.token=r.json()["access_token"]
    g=api.post("/api/groups", json={"name": f"矩阵验收-{SUF}", "description":"matrix"}).json()
    return g["id"]

def main():
    api=Api(); gid=run(seed(api))

    # 1) 导入格式
    r=api.get("/api/accounts/import/formats")
    kinds=[f["kind"] for f in r.json().get("formats", [])]
    check("导入格式接口", r.status_code==200 and set(kinds)=={"phone","session_string","session_file","tdata"}, kinds)
    check("tdata 可用性已上报", "tdata_available" in r.json(), r.json().get("tdata_available"))

    # 2) 手机号清单预览
    phones="+113800138001,备注\n+113900139002\nbad-number\n# 注释行"
    r=api.post("/api/accounts/import/parse", data={"kind":"phone","text":phones})
    body=r.json()
    check("手机号预览解析", r.status_code==200 and body["total"]==3 and body["failed"]==1, f"total={body.get('total')} failed={body.get('failed')}")

    # 3) 正式导入（手机号，走待登录）
    r=api.post("/api/accounts/import", data={"kind":"phone","text":phones,"group_id":gid,"remark":f"矩阵批-{SUF}","start_warmup":"true"})
    body=r.json()
    check("手机号导入落库", r.status_code==200 and body["succeeded"]==2 and body["failed"]==1, body.get("message"))
    check("导入批次返回", bool(body.get("batch_id")), body.get("batch_id"))

    # 4) 重复导入去重
    r=api.post("/api/accounts/import", data={"kind":"phone","text":"+113800138001\n+113900139002"})
    check("重复号码被识别为重复", r.json().get("duplicate")==2, r.json().get("duplicate"))

    # 5) 伪造 session 串：应当解析失败并被标红（不写库）
    r=api.post("/api/accounts/import/parse", data={"kind":"session_string","text":"not-a-session-string"})
    check("非法 session 串被拦", r.json().get("failed",0)>=1, r.json().get("failed"))

    # 6) 上传一个假的 sqlite 文件（非 SQLite）应报错而不是 500
    r=api.post("/api/accounts/import/parse", data={"kind":"session_file"}, files={"files":("x.session", io.BytesIO(b"not sqlite"), "application/octet-stream")})
    check("非 SQLite 文件给出明确错误", r.status_code==200 and r.json().get("failed")==1, r.json().get("items",[{}])[0].get("error","")[:60])

    # 7) 批量节流
    accs=[i["account_id"] for i in body.get("results",[]) if i.get("ok")]
    r=api.post("/api/accounts/bulk/throttle", json={"account_ids":accs,"daily_message_limit":30,"min_action_seconds":45,"start_warmup_now":True,"reset_flood":True})
    check("批量节流设置", r.status_code==200 and r.json()["succeeded"]==2, r.json().get("message"))

    # 8) 深度验活入队
    r=api.post("/api/accounts/bulk/probe", json={"account_ids":accs,"write_probe":False})
    check("深度验活入队", r.status_code==200 and r.json()["succeeded"]==2, r.json().get("message"))

    # 9) 账号出参带矩阵字段 + matrix 接口
    r=api.get("/api/accounts", params={"page":1,"page_size":5,"keyword":""})
    items=r.json().get("items",[])
    one=[i for i in items if i["id"] in accs]
    check("账号出参含健康分/来源", bool(one) and "health_score" in one[0] and one[0]["import_source"]=="phone", one[0].get("health_score") if one else None)
    r=api.get(f"/api/accounts/{accs[0]}/matrix")
    check("矩阵状态接口", r.status_code==200 and "throttle" in r.json(), list(r.json().keys())[:6])
    th=r.json().get("throttle",{})
    check("节流快照含额度", th.get("daily_limit")==30 and th.get("min_interval_seconds")==45, th)

    # 10) 批次列表
    r=api.get("/api/accounts/import/batches")
    check("导入批次列表", r.status_code==200 and len(r.json())>=1, len(r.json()))

    # 清理
    async def cleanup():
        from sqlalchemy import delete, select
        from app import db
        from app.models import AccountGroup, AccountImport, TgAccount
        async with db.SessionFactory() as s:
            for aid in accs:
                row=await s.scalar(select(TgAccount).where(TgAccount.id==uuid.UUID(aid)))
                if row: await s.delete(row)
            grp=await s.scalar(select(AccountGroup).where(AccountGroup.id==uuid.UUID(gid)))
            if grp: await s.delete(grp)
            await s.execute(delete(AccountImport).where(AccountImport.remark.like(f"%{SUF}%")))
            await s.commit()
    run(cleanup())

    print(f"\n通过 {len(PASS)}，失败 {len(FAIL)}")
    for n in FAIL: print("  x", n)
    sys.exit(1 if FAIL else 0)

main()
