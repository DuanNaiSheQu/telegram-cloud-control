#!/usr/bin/env python3
"""部署产物的静态校验：不依赖 docker，也能在本地提前发现接线错误。

    cd backend && .venv/bin/python ../scripts/check_stack_config.py

覆盖：
1. 4 个 YAML 能否解析；
2. compose 服务名 / depends_on / 构建上下文 / 挂载源是否真实存在；
3. 告警规则条数、四条规划告警引用的指标、每条告警都有中文 summary（录制规则除外）；
4. `.env.example` 是否覆盖 `app/config.py` 的全部字段、真实密钥是否留空；
5. 前端 nginx 是否反代 api 且支持 WebSocket 升级。

真机还需要在有 docker 的机器上跑 `docker compose config` / `promtool` / `amtool`。
"""

from __future__ import annotations

import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
FAILED: list[str] = []
PASSED = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASSED
    if cond:
        PASSED += 1
        print(f"  ✅ {name}{(' — ' + detail) if detail else ''}")
    else:
        FAILED.append(name)
        print(f"  ❌ {name}{(' — ' + detail) if detail else ''}")


def main() -> int:
    print("1) YAML 解析")
    docs: dict = {}
    for rel in ("docker-compose.yml", "deploy/prometheus.yml", "deploy/alert.rules.yml", "deploy/alertmanager.yml"):
        path = ROOT / rel
        try:
            docs[rel] = yaml.safe_load(path.read_text(encoding="utf-8"))
            check(rel, True)
        except Exception as exc:  # noqa: BLE001
            check(rel, False, str(exc))

    print("2) compose 接线")
    compose = docs.get("docker-compose.yml") or {}
    services = compose.get("services") or {}
    names = set(services)
    check("基础服务齐全", {"postgres", "redis", "api", "worker", "frontend"} <= names, str(sorted(names)))
    for name, spec in services.items():
        depends = spec.get("depends_on")
        deps = list(depends) if isinstance(depends, dict) else (depends or [])
        missing = [d for d in deps if d not in names]
        check(f"{name}.depends_on 指向存在的服务", not missing, str(missing))

        context = (spec.get("build") or {}).get("context")
        if context:
            check(f"{name} 构建上下文存在", (ROOT / context).is_dir(), context)
        for volume in spec.get("volumes", []) or []:
            source = str(volume).split(":")[0]
            if source.startswith("./"):
                check(f"{name} 挂载源存在", (ROOT / source).exists(), source)

    print("3) 告警规则")
    groups = (docs.get("deploy/alert.rules.yml") or {}).get("groups") or []
    alerts = [rule for group in groups for rule in group.get("rules", []) if "alert" in rule]
    records = [rule for group in groups for rule in group.get("rules", []) if "record" in rule]
    check("有告警规则", bool(alerts), f"{len(alerts)} 条告警 / {len(records)} 条录制规则")
    expressions = "\n".join(rule.get("expr", "") for rule in alerts + records)
    for metric in (
        "tgcc_worker_heartbeat_age_seconds",   # 告警 1：Worker 心跳
        "tgcc_online_accounts",                # 告警 2：在线号比例
        "tgcc_tasks",                          # 告警 3：失败 / 到期任务
        "tgcc_last_successful_backup_timestamp_seconds",  # 告警 4：备份
    ):
        check(f"规划四条告警覆盖 {metric}", metric in expressions)
    missing_summary = [rule.get("alert") for rule in alerts if not (rule.get("annotations") or {}).get("summary")]
    check("每条告警都有 summary（录制规则不需要）", not missing_summary, str(missing_summary[:3]))

    print("4) .env.example ↔ app/config.py")
    sys.path.insert(0, str(ROOT / "backend"))
    from app.config import Settings  # noqa: E402  (放这里是为了先打印上面几节)

    fields = set(Settings.model_fields)
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    env_keys = {m.group(1).lower() for m in re.finditer(r"^([A-Z][A-Z0-9_]*)=.*$", text, re.M)}
    missing = sorted(fields - env_keys)
    check("config.py 字段都被样例覆盖", not missing, f"缺 {missing}")

    # 真实的密钥类必须留空；样例里只允许出现明确的占位值
    placeholders = {"change-me-postgres-password", "cloudctl", "admin", ""}
    leaked = []
    for key in ("SECRET_KEY", "SESSION_ENCRYPTION_KEY", "TELEGRAM_API_HASH", "WEBHOOK_SECRET", "AI_API_KEY", "BOOTSTRAP_ADMIN_PASSWORD", "POSTGRES_PASSWORD"):
        match = re.search(rf"^{key}=(.*)$", text, re.M)
        value = (match.group(1).strip() if match else "")
        if value and value not in placeholders:
            leaked.append(f"{key}={value[:12]}")
    check("密钥类只留空或占位值", not leaked, str(leaked))

    print("5) 前端部署")
    dockerfile = ROOT / "frontend" / "Dockerfile"
    nginx = ROOT / "frontend" / "nginx.conf"
    check("frontend/Dockerfile 存在", dockerfile.exists())
    check("frontend/nginx.conf 存在", nginx.exists())
    if nginx.exists():
        conf = nginx.read_text(encoding="utf-8")
        check("nginx 反代 api:8000", "api:8000" in conf)
        check("nginx 支持 WebSocket 升级", "Upgrade" in conf and "connection_upgrade" in conf)
        check("nginx 走 SPA 回退", "try_files" in conf)

    print()
    print(f"== 结论：{PASSED} 通过 / {len(FAILED)} 失败 ==")
    for name in FAILED:
        print(f"  FAIL: {name}")
    print("（真机还需 docker compose config、promtool check rules/config、amtool check-config）")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
