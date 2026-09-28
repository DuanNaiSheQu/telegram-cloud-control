#!/usr/bin/env python3
"""端到端验收：只打 HTTP / WebSocket /metrics，不直连数据库，可在任意环境复跑。

    .venv/bin/python scripts/e2e_check.py
    .venv/bin/python scripts/e2e_check.py --base-url http://127.0.0.1:8000 --worker-metrics http://127.0.0.1:9101

先起整套：`./scripts/stack_local.sh up`。脚本会自建测试数据并在结束时清理。
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from typing import Any, Optional

import httpx

PASSED: list[str] = []
FAILED: list[str] = []
SKIPPED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    if ok:
        PASSED.append(name)
        print(f"  ✅ {name}{(' — ' + str(detail)) if detail else ''}")
    else:
        FAILED.append(name)
        print(f"  ❌ {name}{(' — ' + str(detail)) if detail else ''}")
    return ok


def skip(name: str, why: str) -> None:
    SKIPPED.append(f"{name}（{why}）")
    print(f"  ⏭  {name} — 跳过：{why}")


class Api:
    def __init__(self, base_url: str, timeout: float = 20.0) -> None:
        self.client = httpx.Client(base_url=base_url, timeout=timeout)
        self.token: Optional[str] = None

    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.update(self.headers())
        return self.client.request(method, url, headers=headers, **kwargs)

    def get(self, url: str, **kw) -> httpx.Response:
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw) -> httpx.Response:
        return self.request("POST", url, **kw)

    def patch(self, url: str, **kw) -> httpx.Response:
        return self.request("PATCH", url, **kw)

    def delete(self, url: str, **kw) -> httpx.Response:
        return self.request("DELETE", url, **kw)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--worker-metrics", default="http://127.0.0.1:9101")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin12345")
    args = parser.parse_args()

    suffix = uuid.uuid4().hex[:6]
    api = Api(args.base_url)
    created: dict[str, list[str]] = {"accounts": [], "groups": [], "proxies": [], "users": []}
    worker_alive = False

    try:
        # ---------- 1. 探测接口 ----------
        print("1) 运维探测")
        r = api.get("/health")
        check("/health 进程活着", r.status_code == 200 and r.json().get("status") == "ok", r.text[:120])
        r = api.get("/ready")
        ready = r.status_code == 200
        check("/ready 数据库与 Redis 都通", ready and r.json().get("database") is True and r.json().get("redis") is True,
              r.text[:160])
        r = api.get("/metrics")
        check("/metrics 是 Prometheus 文本", r.status_code == 200 and "tgcc_" in r.text,
              r.text.strip().splitlines()[0][:80] if r.text.strip() else "空响应")

        try:
            wm = httpx.get(f"{args.worker_metrics.rstrip('/')}/metrics", timeout=5)
            worker_alive = wm.status_code == 200 and "tgcc_online_accounts" in wm.text
        except Exception:  # noqa: BLE001
            worker_alive = False
        if worker_alive:
            check("worker /metrics 有在线号等指标", True, "tgcc_online_accounts 存在")
        else:
            skip("worker /metrics", "worker 没在跑（`./scripts/stack_local.sh up` 可拉起）")

        # ---------- 2. 鉴权 ----------
        print("2) 鉴权与权限")
        r = api.post("/api/auth/login", json={"username": args.username, "password": "definitely-wrong"})
        check("错误口令被拒", r.status_code in (400, 401), f"HTTP {r.status_code}")
        r = api.post("/api/auth/login", json={"username": args.username, "password": args.password})
        if r.status_code != 200:
            check("管理员登录", False, f"HTTP {r.status_code} {r.text[:200]}（先跑 scripts/create_admin.py）")
            raise SystemExit(1)
        api.token = r.json()["access_token"]
        check("管理员登录拿到 JWT", bool(api.token))
        r = api.get("/api/auth/me")
        check("/api/auth/me 返回当前用户", r.status_code == 200 and r.json().get("username") == args.username)
        r = api.get("/api/accounts")
        check("无 token 访问被拒", httpx.get(f"{args.base_url}/api/accounts", timeout=10).status_code == 401)

        # ---------- 3. 基础数据 ----------
        print("3) 分组 / 代理 / 账号 / 员工分配")
        r = api.post("/api/groups", json={"name": f"验收分组-{suffix}", "description": "e2e"})
        check("建分组", r.status_code in (200, 201), r.text[:160])
        group_id = r.json().get("id") if r.status_code in (200, 201) else None
        if group_id:
            created["groups"].append(group_id)

        r = api.post("/api/proxies", json={
            "name": f"验收代理-{suffix}", "scheme": "socks5", "host": "127.0.0.1", "port": 1080,
            "username": "u", "password": "p",
        })
        check("建代理（口令加密保存，只回 has_auth）",
              r.status_code in (200, 201) and r.json().get("has_auth") is True and "password" not in r.json(),
              r.text[:160])
        proxy_id = r.json().get("id") if r.status_code in (200, 201) else None
        if proxy_id:
            created["proxies"].append(proxy_id)

        account_ids: list[str] = []
        for i in (1, 2):
            r = api.post("/api/accounts", json={
                "phone": f"+8613800{int(suffix, 16) % 100000:05d}{i}",
                "group_id": group_id, "proxy_id": proxy_id, "remark": f"e2e-{i}",
            })
            ok = r.status_code in (200, 201)
            check(f"建账号 #{i}（手机号脱敏）", ok and "****" in r.json().get("phone_masked", ""), r.text[:160])
            if ok:
                account_ids.append(r.json()["id"])
                created["accounts"].append(r.json()["id"])
        if len(account_ids) < 2:
            raise SystemExit(1)

        r = api.get("/api/accounts", params={"page": 1, "page_size": 50})
        body = r.json()
        check("账号列表带四块汇总", r.status_code == 200 and body.get("summary", {}).get("total", 0) >= 2,
              str(body.get("summary")))
        r = api.get("/api/accounts/summary")
        check("/api/accounts/summary 可用", r.status_code == 200 and "abnormal" in r.json(), r.text[:120])
        r = api.get("/api/accounts", params={"status": "pending", "page_size": 50})
        check("按状态筛选生效", r.status_code == 200 and all(i["status"] == "pending" for i in r.json()["items"]))
        r = api.get("/api/accounts", params={"group_id": group_id, "page_size": 50})
        check("按分组筛选生效", r.status_code == 200 and len(r.json()["items"]) >= 2)
        # 用真实脱敏值的前 3 位做关键词（形如 861****2551）：脱敏后前 3 位是国家码 + 号段开头
        probe = api.get("/api/accounts", params={"page_size": 50}).json()["items"][0]["phone_masked"][:3]
        r = api.get("/api/accounts", params={"phone": probe, "page_size": 50})
        check("按手机号筛选生效", r.status_code == 200 and len(r.json()["items"]) >= 1, f"keyword={probe}")

        # 契约没写解绑接口，前端走 PATCH 显式 null；这里验证后端确实按「显式设置」处理
        r = api.patch(f"/api/accounts/{account_ids[0]}", json={"proxy_id": None})
        check("代理解绑（PATCH 显式 null）生效",
              r.status_code == 200 and r.json().get("proxy_id") is None, r.text[:160])
        r = api.patch(f"/api/accounts/{account_ids[0]}", json={"proxy_id": proxy_id})
        check("代理重新绑定生效", r.status_code == 200 and r.json().get("proxy_id") == proxy_id)

        r = api.post("/api/users", json={
            "username": f"e2e-op-{suffix}", "password": "op-pass-1234", "display_name": "验收员工",
            "role": "operator",
        })
        check("建 operator 员工", r.status_code in (200, 201), r.text[:200])
        operator_id = r.json().get("id") if r.status_code in (200, 201) else None
        if operator_id:
            created["users"].append(operator_id)
            r = api.post("/api/assignments", json={"user_id": operator_id, "account_ids": [account_ids[0]]})
            check("把 1 号账号分配给员工", r.status_code in (200, 201), r.text[:200])

        # ---------- 4. 任务与检测 ----------
        print("4) 任务中心与账号检测")
        r = api.post(f"/api/accounts/{account_ids[0]}/check")
        check("单号检测返回任务", r.status_code == 200 and r.json().get("account_id") == account_ids[0], r.text[:200])
        r = api.post(f"/api/accounts/{account_ids[1]}/sync-dialogs")
        check("同步会话写出任务", r.status_code == 200, r.text[:200])

        r = api.post("/api/accounts/login/start", json={"account_id": account_ids[0]})
        check("登录第一步返回 code_required",
              r.status_code == 200 and r.json().get("step") in ("code_required", "pending", "submitted"),
              r.text[:200])

        task_id = None
        for _ in range(15):
            r = api.get("/api/tasks", params={"type": "account_check", "page_size": 20})
            if r.status_code == 200:
                items = r.json().get("items", [])
                if items:
                    task_id = items[0]["id"]
                    check("任务中心能查到检测任务", True,
                          f"status={items[0]['status']} attempts={items[0]['attempts']} label={items[0].get('type_label')}")
                    break
            time.sleep(1)
        if task_id is None:
            check("任务中心能查到检测任务", False, "15 秒内没查到 account_check 任务")

        if task_id:
            if worker_alive:
                got = None
                for _ in range(20):
                    r = api.get(f"/api/tasks/{task_id}")
                    if r.status_code == 200:
                        got = r.json()
                        if got["status"] in ("failed", "completed") or got["attempts"] >= 1:
                            break
                    time.sleep(1)
                check("worker 领取并处理了任务（无 Telegram 凭证时记为失败/重试）",
                      bool(got) and (got["attempts"] >= 1 or got["status"] in ("failed", "completed")),
                      f"status={got and got['status']} attempts={got and got['attempts']} error={(got or {}).get('error','')[:80]}")
                check("失败原因是人能看懂的中文", bool(got) and (not got["error"] or any("\u4e00" <= c <= "\u9fff" for c in got["error"])),
                      (got or {}).get("error", "")[:100])
            else:
                skip("worker 执行任务", "worker 没在跑")

        r = api.get("/api/tasks", params={"page_size": 5})
        check("任务列表带状态汇总", r.status_code == 200 and isinstance(r.json().get("counts"), dict),
              str(r.json().get("counts"))[:120])

        # ---------- 5. 会话 / 转发 / Bot ----------
        print("5) 会话 / 转发 / Bot")
        r = api.get("/api/dialogs", params={"page_size": 10})
        check("会话列表可用（无消息时为空列表）", r.status_code == 200 and "items" in r.json(), r.text[:120])
        r = api.get("/api/dialogs", params={"channel": "bot", "page_size": 10})
        check("会话按通道筛选可用", r.status_code == 200)
        r = api.get("/api/relays")
        check("转发规则列表可用", r.status_code == 200, r.text[:120])
        r = api.get("/api/bots")
        check("Bot 列表可用", r.status_code == 200, r.text[:120])
        r = api.post("/api/bots", json={"name": f"e2e-bot-{suffix}", "token": "123456:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"})
        check("无效 Bot Token 被拒且不是 500（无外网/无凭证环境的预期行为）",
              r.status_code in (400, 409, 422, 502, 503), f"HTTP {r.status_code} {r.text[:120]}")

        # ---------- 6. 审计 ----------
        print("6) 审计与操作记录")
        r = api.get("/api/audit", params={"page_size": 20})
        check("审计表有记录", r.status_code == 200 and r.json().get("total", 0) >= 1,
              f"total={r.json().get('total') if r.status_code == 200 else 'n/a'}")

        # ---------- 7. 权限边界 ----------
        print("7) 员工可见范围")
        if operator_id:
            op = Api(args.base_url)
            r = op.post("/api/auth/login", json={"username": f"e2e-op-{suffix}", "password": "op-pass-1234"})
            if check("operator 能登录", r.status_code == 200, r.text[:120]):
                op.token = r.json()["access_token"]
                r = op.get("/api/accounts", params={"page_size": 50})
                ids = [i["id"] for i in r.json().get("items", [])] if r.status_code == 200 else []
                check("operator 只看得到被分配的号", ids == [account_ids[0]], f"visible={len(ids)}")
                r = op.get(f"/api/accounts/{account_ids[1]}")
                check("operator 访问未分配账号被拒 (403)", r.status_code == 403, f"HTTP {r.status_code}")
                r = op.post("/api/users", json={"username": "x", "password": "y" * 8})
                check("operator 不能建员工 (403)", r.status_code == 403, f"HTTP {r.status_code}")

        # ---------- 8. WebSocket ----------
        print("8) WebSocket 实时通道")
        try:
            from websockets.sync.client import connect as ws_connect

            with ws_connect(f"{args.base_url.replace('http', 'ws', 1)}/api/ws?token={api.token}",
                            open_timeout=8) as ws:
                hello = ws.recv(timeout=8)
                check("连接后收到 hello", "hello" in hello, hello[:100])
                ws.send('{"op":"ping"}')
                pong = ws.recv(timeout=8)
                check("ping 收到 pong", "pong" in pong, pong[:100])
                ws.send(f'{{"op":"subscribe","dialog_ids":["{uuid.uuid4()}"]}}')
                check("subscribe 不报错", True)
        except Exception as exc:  # noqa: BLE001
            check("WebSocket 可连接", False, f"{type(exc).__name__}: {exc}")

    finally:
        # ---------- 清理 ----------
        print("9) 清理测试数据")
        if api.token:
            for account_id in created["accounts"]:
                api.delete(f"/api/accounts/{account_id}")
            for user_id in created["users"]:
                api.delete(f"/api/users/{user_id}")
            for proxy_id in created["proxies"]:
                api.delete(f"/api/proxies/{proxy_id}")
            for group_id in created["groups"]:
                api.delete(f"/api/groups/{group_id}")
            print(f"  已清理：账号 {len(created['accounts'])}、员工 {len(created['users'])}、"
                  f"代理 {len(created['proxies'])}、分组 {len(created['groups'])}")
        api.client.close()

    print()
    print(f"== 验收结果：{len(PASSED)} 通过 / {len(FAILED)} 失败 / {len(SKIPPED)} 跳过 ==")
    for name in FAILED:
        print(f"  FAIL: {name}")
    for name in SKIPPED:
        print(f"  SKIP: {name}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
