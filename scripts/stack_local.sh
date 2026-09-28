#!/usr/bin/env bash
# 本地（不用 Docker）起停整套服务，用于端到端验收。
#   ./scripts/stack_local.sh up      起 api + worker（后台，日志在 run/）
#   ./scripts/stack_local.sh down    优雅停（worker 先 SIGTERM 释放租约，再停 api）
#   ./scripts/stack_local.sh status  看进程与探测结果
#   ./scripts/stack_local.sh logs    跟日志
# 依赖：backend/.venv、backend/.env、本机可用的 Postgres 与 Redis（地址写在 .env 里）。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
RUN="$ROOT/run"
VENV_PY="$BACKEND/.venv/bin/python"
API_PORT="${API_PORT:-8000}"
WORKER_METRICS_PORT="${WORKER_METRICS_PORT:-9101}"
mkdir -p "$RUN"

need() { [ -x "$1" ] || { echo "缺少 $1（先按 README 准备 venv）" >&2; exit 1; }; }
env_file() { [ -f "$BACKEND/.env" ] || { echo "缺少 backend/.env（从 .env.example 复制）" >&2; exit 1; }; }

case "${1:-up}" in
  up)
    need "$VENV_PY"; env_file
    echo "[1/4] 数据库迁移"
    (cd "$BACKEND" && "$VENV_PY" -m alembic upgrade head)
    echo "[2/4] 建/重置管理员（BOOTSTRAP_ADMIN_PASSWORD 为空则跳过）"
    if grep -q '^BOOTSTRAP_ADMIN_PASSWORD=.\+' "$BACKEND/.env" 2>/dev/null; then
      (cd "$BACKEND" && "$VENV_PY" "$ROOT/scripts/create_admin.py") || true
    else
      echo "  BOOTSTRAP_ADMIN_PASSWORD 未设置，跳过"
    fi
    echo "[3/4] 启动 api :$API_PORT"
    (cd "$BACKEND" && nohup "$VENV_PY" -m uvicorn app.api.main:app --host 127.0.0.1 --port "$API_PORT" \
      >"$RUN/api.log" 2>&1 & echo $! >"$RUN/api.pid")
    for _ in $(seq 1 30); do
      if curl -fsS "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1; then break; fi
      sleep 1
    done
    echo "[4/4] 启动 worker（metrics :$WORKER_METRICS_PORT）"
    (cd "$BACKEND" && nohup "$VENV_PY" -m app.worker.main \
      >"$RUN/worker.log" 2>&1 & echo $! >"$RUN/worker.pid")
    sleep 3
    echo "--- /ready ---"; curl -s "http://127.0.0.1:$API_PORT/ready"; echo
    echo "--- 日志尾部 ---"; tail -n 5 "$RUN/worker.log" || true
    ;;
  down)
    if [ -f "$RUN/worker.pid" ]; then
      pid=$(cat "$RUN/worker.pid")
      echo "停 worker $pid（SIGTERM，先释放租约）"
      kill -TERM "$pid" 2>/dev/null || true
      for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
      kill -KILL "$pid" 2>/dev/null || true
      rm -f "$RUN/worker.pid"
    fi
    if [ -f "$RUN/api.pid" ]; then
      pid=$(cat "$RUN/api.pid"); echo "停 api $pid"
      kill -TERM "$pid" 2>/dev/null || true
      for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
      kill -KILL "$pid" 2>/dev/null || true
      rm -f "$RUN/api.pid"
    fi
    ;;
  status)
    for name in api worker; do
      if [ -f "$RUN/$name.pid" ] && kill -0 "$(cat "$RUN/$name.pid")" 2>/dev/null; then
        echo "$name: 运行中 (pid $(cat "$RUN/$name.pid"))"
      else
        echo "$name: 未运行"
      fi
    done
    curl -s "http://127.0.0.1:$API_PORT/health" || echo "（api /health 不可达）"; echo
    curl -s "http://127.0.0.1:$API_PORT/ready" || echo "（api /ready 不可达）"; echo
    curl -s "http://127.0.0.1:$WORKER_METRICS_PORT/metrics" | grep -E '^tgcc_' | head -12 || echo "（worker /metrics 不可达）"
    ;;
  logs)
    tail -f "$RUN/api.log" "$RUN/worker.log"
    ;;
  *)
    echo "用法：$0 {up|down|status|logs}" >&2; exit 2
    ;;
esac
