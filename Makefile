# Telegram 云控 —— 常用操作
#
# 所有 docker 相关 target 都假设在仓库根目录执行（这里有 docker-compose.yml 和 .env）。
# 本机没有 docker 时只用 dev-* 那几个 target 直接跑进程。
# 每个 target 上面的 ## 注释会被 make help 读出来。

SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE ?= docker compose
VENV ?= backend/.venv
PY ?= $(VENV)/bin/python
API_PORT ?= 8000
M ?= auto
ADMIN_PASSWORD ?=
ADMIN_ENV := $(if $(ADMIN_PASSWORD),-e BOOTSTRAP_ADMIN_PASSWORD='$(ADMIN_PASSWORD)')

## 显示本帮助（默认）
help:
	@echo "Telegram 云控 —— 可用 target："
	@awk '/^## /{desc=substr($$0,4); next} /^[a-zA-Z0-9_.-]+:/{if(desc!=""){n=$$1; sub(/:$$/,"",n); printf "  %-14s %s\n", n, desc; desc=""}}' $(MAKEFILE_LIST)
	@echo ""
	@echo "变量：COMPOSE='$(COMPOSE)'  VENV='$(VENV)'  API_PORT='$(API_PORT)'"
	@echo "例：make logs S=worker / make revision M=\"add relay tables\" / make admin ADMIN_PASSWORD='xxx'"

## 启动全部服务（postgres/redis/api/worker/frontend）
up:
	@mkdir -p backups
	$(COMPOSE) up -d --build

## 停止全部服务（含监控 profile；数据卷保留）
down:
	$(COMPOSE) --profile monitoring down

## 跟踪日志（默认全部，make logs S=worker 只看一个服务）
logs:
	$(COMPOSE) logs -f --tail=200 $(S)

## 看容器状态与健康检查结果
ps:
	$(COMPOSE) ps

## 数据库迁移（api 没在跑时自动用一次性容器）
migrate:
	@if $(COMPOSE) ps --status running --services 2>/dev/null | grep -qx api; then \
		echo "==> 在运行中的 api 容器里执行 alembic upgrade head"; \
		$(COMPOSE) exec -T api alembic upgrade head; \
	else \
		echo "==> api 未运行，改用一次性容器执行迁移"; \
		$(COMPOSE) run --rm api alembic upgrade head; \
	fi

## 生成迁移脚本（make revision M="描述"）
revision:
	@test -n "$(M)" || { echo "用法：make revision M=\"改动描述\""; exit 2; }
	$(COMPOSE) run --rm api alembic revision --autogenerate -m "$(M)"

## 创建/重置管理员（口令默认读 .env，可用 ADMIN_PASSWORD 覆盖）
admin:
	@if $(COMPOSE) ps --status running --services 2>/dev/null | grep -qx api; then \
		$(COMPOSE) exec -T $(ADMIN_ENV) api /app/entrypoint.sh --bootstrap-admin; \
	else \
		echo "==> api 未运行，改用一次性容器创建管理员"; \
		$(COMPOSE) run --rm $(ADMIN_ENV) api --bootstrap-admin; \
	fi

## 启动监控栈（prometheus/alertmanager/pushgateway/postgres-exporter）
monitoring:
	$(COMPOSE) --profile monitoring up -d
	@echo "Prometheus   http://localhost:$${PROMETHEUS_PORT:-9090}"
	@echo "Alertmanager http://localhost:$${ALERTMANAGER_PORT:-9093}"

## 立即备份一次（日备 + 周备，详见 deploy/backup.sh）
backup:
	@mkdir -p backups
	bash deploy/backup.sh all

## 恢复指引（真正的恢复照 deploy/postgres-backup.md 手动做）
restore:
	@echo "恢复步骤见 deploy/postgres-backup.md，这里只列入口："
	@echo "  1) 校验最新日备（只读，不碰生产库）："
	@echo "     pg_restore -l \$$(ls -1t backups/daily-*.dump | head -1) | head"
	@echo "  2) 日常误删 -> 逻辑恢复：整库替换或单表导回，见文档第 3 节"
	@echo "     $(COMPOSE) stop api worker"
	@echo "     $(COMPOSE) exec -T postgres pg_restore -U cloudctl -d cloudctl --no-owner < backups/daily-<时间戳>.dump"
	@echo "  3) 按时间点恢复（PITR）：base-*.tar.gz + WAL 归档，见文档第 4 节"
	@echo "  4) 恢复后重启并自检：$(COMPOSE) start api worker && curl -fsS http://127.0.0.1:8000/ready"

## 本地跑 API（不用 docker；读 backend/.env）
dev-api:
	cd backend && .venv/bin/uvicorn app.api.main:app --reload --host 0.0.0.0 --port $(API_PORT)

## 本地跑 Worker（不用 docker）
dev-worker:
	cd backend && .venv/bin/python -m app.worker.main

## 本地跑前端 dev server（不用 docker）
dev-web:
	cd frontend && npm run dev

## 进 psql 排查
psql:
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-cloudctl} -d $${POSTGRES_DB:-cloudctl}

## 语法检查：Python 编译 + 前端 tsc
check:
	@echo "==> Python 语法检查"
	@$(PY) -m compileall -q backend/app backend/alembic scripts && echo "Python 编译通过"
	@echo "==> 前端类型检查（frontend/package.json 的 typecheck）"
	@if [ -d frontend/node_modules ]; then cd frontend && npm run -s typecheck && echo "tsc 通过"; else echo "跳过：frontend/node_modules 未安装（先 cd frontend && npm ci）"; fi

## 本地起 api + worker（不用 docker，含迁移与建管理员，日志在 run/）
stack-up:
	./scripts/stack_local.sh up

## 停本地 api + worker（worker 先 SIGTERM 释放租约）
stack-down:
	./scripts/stack_local.sh down

## 本地进程与探测状态
stack-status:
	./scripts/stack_local.sh status

## 共享层冒烟（需本地 Postgres/Redis，读 backend/.env）
smoke:
	cd backend && .venv/bin/python -m tests.smoke_core
	cd backend && .venv/bin/python -m tests.smoke_ai

## 端到端验收（需先 make stack-up）
e2e:
	$(PY) scripts/e2e_check.py

## 控制台新接口验收：批量/导出/详情聚合/趋势/通知/排序搜索（需先 make stack-up）
console-check:
	cd backend && .venv/bin/python -m tests.console_api
	cd backend && .venv/bin/python -m tests.console_extra
	cd backend && .venv/bin/python -m tests.console_delete
	cd backend && .venv/bin/python -m tests.console_filter

## 静态校验部署产物（compose / 告警规则 / .env.example / nginx）
config-check:
	$(PY) scripts/check_stack_config.py

.PHONY: help up down logs ps migrate revision admin monitoring backup restore dev-api dev-worker dev-web psql check \
	stack-up stack-down stack-status smoke e2e console-check config-check
