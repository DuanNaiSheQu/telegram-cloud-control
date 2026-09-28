#!/usr/bin/env bash
# Telegram 云控 —— API / Worker 统一入口
#
# 职责：
#   ROLE=api    ：等 Postgres -> 生产密钥自检 -> alembic upgrade head -> 可选建管理员 -> exec 命令
#   ROLE=worker ：等 Postgres -> 等表结构（迁移完成）-> exec 命令（SIGTERM 由 app 自己处理租约释放）
#   其它 ROLE   ：原样透传命令（CI、psql、一次性脚本）
#
# 管理员初始化说明：
#   scripts/create_admin.py 在 backend/ 构建上下文之外（context=./backend），且约定不改 scripts/，
#   所以这里用内联 python 完成等价的 upsert（与脚本同样调用 app.models.User + app.security.hash_password）。
#   内置两条路径：
#     ensure（API 启动时自动跑）：只在管理员不存在时创建，绝不覆盖已改过的口令；
#     force （make admin / entrypoint.sh --bootstrap-admin）：创建或重置口令。
#
# 手动用法：
#   docker compose exec -T api /app/entrypoint.sh --bootstrap-admin
#   docker compose run --rm api /app/entrypoint.sh --bootstrap-admin

set -euo pipefail

APP_DIR=/app
cd "$APP_DIR"

DB_WAIT_ATTEMPTS="${DB_WAIT_ATTEMPTS:-60}"            # 60 * 2s = 120s，等 Postgres 起来
DB_WAIT_INTERVAL="${DB_WAIT_INTERVAL:-2}"
SCHEMA_WAIT_ATTEMPTS="${SCHEMA_WAIT_ATTEMPTS:-150}"   # 150 * 2s = 300s，等 api 跑完迁移

log() { printf '[entrypoint] %s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"; }
die() { printf '[entrypoint] 错误：%s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'USAGE'
用法：
  entrypoint.sh [--bootstrap-admin] [命令 [参数...]]

  --bootstrap-admin   仅创建/重置管理员（读 BOOTSTRAP_ADMIN_USERNAME / BOOTSTRAP_ADMIN_PASSWORD）后退出
  无参数              按 ROLE=api|worker 做启动前检查，然后 exec 默认命令

环境变量：
  ROLE                     api | worker（默认 api）
  DB_WAIT_ATTEMPTS         等库重试次数，默认 60（每次 2 秒）
  DB_WAIT_INTERVAL         重试间隔秒数，默认 2
  SCHEMA_WAIT_ATTEMPTS     Worker 等迁移完成的重试次数，默认 150
USAGE
}

# ---------------------------------------------------------------- 等待依赖

wait_for_postgres() {
  local i=1
  log "等待 Postgres 就绪（最多 $((DB_WAIT_ATTEMPTS * DB_WAIT_INTERVAL)) 秒）..."
  while [ "$i" -le "$DB_WAIT_ATTEMPTS" ]; do
    if python - <<'PY'
import asyncio
import sys

from app.db import ping_database

sys.exit(0 if asyncio.run(ping_database()) else 1)
PY
    then
      log "Postgres 已就绪（第 ${i} 次探测）"
      return 0
    fi
    i=$((i + 1))
    sleep "$DB_WAIT_INTERVAL"
  done
  die "Postgres 在 $((DB_WAIT_ATTEMPTS * DB_WAIT_INTERVAL)) 秒内不可用：检查 DATABASE_URL、postgres 健康检查与网络"
}

wait_for_schema() {
  local i=1
  log "等待数据库迁移完成（alembic_version 出现，最多 $((SCHEMA_WAIT_ATTEMPTS * DB_WAIT_INTERVAL)) 秒）..."
  while [ "$i" -le "$SCHEMA_WAIT_ATTEMPTS" ]; do
    if python - <<'PY'
import asyncio
import sys

from sqlalchemy import text

from app.db import engine


async def main() -> int:
    try:
        async with engine.connect() as conn:
            found = await conn.scalar(text("SELECT to_regclass('public.alembic_version')"))
        return 0 if found else 1
    except Exception:  # noqa: BLE001 - 连不上就继续等
        return 1
    finally:
        await engine.dispose()


sys.exit(asyncio.run(main()))
PY
    then
      log "数据库结构已就绪（第 ${i} 次探测）"
      return 0
    fi
    i=$((i + 1))
    sleep "$DB_WAIT_INTERVAL"
  done
  die "等待迁移超时：先执行 make migrate（或 docker compose up -d api），再启动 worker"
}

# ---------------------------------------------------------------- 配置自检

check_secrets() {
  local env_name="${ENVIRONMENT:-development}"
  if [ "$env_name" = "production" ] || [ "$env_name" = "prod" ]; then
    [ -n "${SECRET_KEY:-}" ] || die "ENVIRONMENT=${env_name} 时必须设置 SECRET_KEY"
    [ "${SECRET_KEY}" != "dev-insecure-secret-change-me" ] || die "ENVIRONMENT=${env_name} 时不能使用默认 SECRET_KEY"
    [ -n "${SESSION_ENCRYPTION_KEY:-}" ] || die "ENVIRONMENT=${env_name} 时必须设置 SESSION_ENCRYPTION_KEY（会话 / Bot Token 加密密钥）"
    case "${PUBLIC_BASE_URL:-}" in
      *localhost*|*127.0.0.1*)
        log "警告：ENVIRONMENT=${env_name} 但 PUBLIC_BASE_URL=${PUBLIC_BASE_URL} 不是公网地址，Telegram Webhook 注册会失败"
        ;;
    esac
    [ -n "${TELEGRAM_API_ID:-}" ] && [ "${TELEGRAM_API_ID}" != "0" ] || log "警告：TELEGRAM_API_ID 未设置，用户号登录会失败"
  else
    [ -n "${SECRET_KEY:-}" ] || log "警告：SECRET_KEY 为空，JWT 与派生加密密钥都不安全，仅限本地开发"
    [ -n "${SESSION_ENCRYPTION_KEY:-}" ] || log "警告：SESSION_ENCRYPTION_KEY 为空，将由 SECRET_KEY 派生，仅限本地开发"
  fi
}

# ---------------------------------------------------------------- 管理员

bootstrap_admin() {
  local mode="${1:-ensure}"
  if [ -z "${BOOTSTRAP_ADMIN_PASSWORD:-}" ]; then
    log "未设置 BOOTSTRAP_ADMIN_PASSWORD，跳过管理员初始化"
    return 0
  fi
  log "初始化管理员 ${BOOTSTRAP_ADMIN_USERNAME:-admin}（模式 ${mode}）"
  python - "$mode" <<'PY'
import asyncio
import sys

from sqlalchemy import select

from app.config import settings
from app.db import dispose_engine, session_scope
from app.models import User, UserRole
from app.security import hash_password

mode = sys.argv[1] if len(sys.argv) > 1 else "ensure"


async def main() -> None:
    username = settings.bootstrap_admin_username
    password = settings.bootstrap_admin_password
    if not password:
        print("[entrypoint] BOOTSTRAP_ADMIN_PASSWORD 为空，跳过")
        return
    try:
        async with session_scope() as session:
            user = await session.scalar(select(User).where(User.username == username))
            if user is None:
                session.add(
                    User(
                        username=username,
                        display_name="管理员",
                        password_hash=hash_password(password),
                        role=UserRole.admin,
                        is_active=True,
                    )
                )
                print(f"[entrypoint] 已创建管理员 {username}")
            elif mode == "force":
                # 与 scripts/create_admin.py 一致：重置口令并保证是启用状态的 admin
                user.password_hash = hash_password(password)
                user.role = UserRole.admin
                user.is_active = True
                print(f"[entrypoint] 已重置管理员 {username} 的口令")
            else:
                print(f"[entrypoint] 管理员 {username} 已存在，未改动口令（需要重置：make admin）")
    finally:
        await dispose_engine()


asyncio.run(main())
PY
}

# ---------------------------------------------------------------- 主流程

MODE=normal
case "${1:-}" in
  --bootstrap-admin|--create-admin)
    MODE=admin
    shift
    ;;
  --help|-h)
    usage
    exit 0
    ;;
esac

if [ "$MODE" = "admin" ]; then
  wait_for_postgres
  wait_for_schema
  bootstrap_admin force
  log "管理员初始化完成"
  exit 0
fi

ROLE="${ROLE:-api}"

# 显式执行 alembic 时不再自动迁移（例如 make migrate 走一次性容器）
RUN_MIGRATIONS=1
if [ "${1:-}" = "alembic" ]; then
  RUN_MIGRATIONS=0
fi

case "$ROLE" in
  api)
    check_secrets
    wait_for_postgres
    if [ "$RUN_MIGRATIONS" = "1" ]; then
      log "执行 alembic upgrade head"
      alembic upgrade head
      log "迁移完成（当前版本：$(alembic current 2>/dev/null | tail -n 1 || echo '未知')）"
      bootstrap_admin ensure
    else
      log "命令显式调用了 alembic，跳过自动迁移"
    fi
    ;;
  worker)
    check_secrets
    wait_for_postgres
    wait_for_schema
    ;;
  *)
    log "ROLE=${ROLE}：不做启动前检查，直接透传命令"
    ;;
esac

if [ "$#" -eq 0 ]; then
  die "没有可执行的命令：检查 compose 里的 command 或 entrypoint 参数"
fi

log "启动进程：$*"
exec "$@"
