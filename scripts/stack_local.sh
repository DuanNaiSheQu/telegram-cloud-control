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

# 探测只用带超时的 curl：连接挂住时不能把脚本一起拖死
probe() { curl -fsS -m 3 "$1" 2>/dev/null; }

start_bg() {
  # $1=名字 $2=日志文件，其余=命令。
  # 要点：$! 必须在**没有子 shell 包装**的位置取，否则会拿到错的 PID（down 时误杀脚本自己）；
  # stdin 接 /dev/null、stdout/stderr 进日志文件，脚本退出后服务继续跑（nohup + disown）。
  # macOS 没有 setsid，所以这里不用它。
  local name="$1" log="$2"
  shift 2
  cd "$BACKEND"
  nohup "$@" </dev/null >"$log" 2>&1 &
  local pid=$!
  echo "$pid" >"$RUN/$name.pid"
  disown "$pid" 2>/dev/null || true
  cd "$ROOT"
}

stop_pidfile() {
  local name="$1" pid
  [ -f "$RUN/$name.pid" ] || return 0
  pid="$(cat "$RUN/$name.pid" 2>/dev/null || true)"
  if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
    rm -f "$RUN/$name.pid"
    echo "$name: 本来就没在跑"
    return 0
  fi
  echo "停 $name (pid $pid)"
  kill -TERM "$pid" 2>/dev/null || true
  for _ in $(seq 1 30); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.5
  done
  kill -KILL "$pid" 2>/dev/null || true
  rm -f "$RUN/$name.pid"
}

case "${1:-up}" in
  up)
    [ -x "$VENV_PY" ] || { echo "缺少 backend/.venv（先按 README 准备 venv）" >&2; exit 1; }
    [ -f "$BACKEND/.env" ] || { echo "缺少 backend/.env（从 .env.example 复制）" >&2; exit 1; }

    echo "[1/4] 数据库迁移"
    ( cd "$BACKEND" && "$VENV_PY" -m alembic upgrade head )

    echo "[2/4] 建/重置管理员（BOOTSTRAP_ADMIN_PASSWORD 为空则跳过）"
    if grep -qE '^BOOTSTRAP_ADMIN_PASSWORD=.+' "$BACKEND/.env"; then
      ( cd "$BACKEND" && "$VENV_PY" "$ROOT/scripts/create_admin.py" ) || echo "  建管理员失败（继续）"
    else
      echo "  BOOTSTRAP_ADMIN_PASSWORD 未设置，跳过"
    fi

    echo "[3/4] 启动 api :${API_PORT}（日志 run/api.log）"
    start_bg api "$RUN/api.log" "$VENV_PY" -m uvicorn app.api.main:app --host 127.0.0.1 --port "$API_PORT"
    for _ in $(seq 1 40); do
      probe "http://127.0.0.1:$API_PORT/health" >/dev/null && break
      sleep 1
    done
    if ! probe "http://127.0.0.1:$API_PORT/health" >/dev/null; then
      echo "  API 没起来，看 run/api.log：" >&2
      tail -n 20 "$RUN/api.log" >&2 || true
      exit 1
    fi

    echo "[4/4] 启动 worker（日志 run/worker.log，metrics :${WORKER_METRICS_PORT}）"
    start_bg worker "$RUN/worker.log" "$VENV_PY" -m app.worker.main
    sleep 3

    echo "--- /ready ---"; probe "http://127.0.0.1:$API_PORT/ready" || echo "(不可达)"; echo
    echo "--- worker 指标（节选）---"
    probe "http://127.0.0.1:$WORKER_METRICS_PORT/metrics" | grep -E '^tgcc_(online|leased|worker_info)' || echo "(不可达)"
    echo "--- worker 日志尾部 ---"; tail -n 4 "$RUN/worker.log" || true
    echo
    echo "下一步：backend/.venv/bin/python scripts/e2e_check.py"
    ;;
  down)
    # 先停 worker：SIGTERM 会先释放租约再断开连接，别的副本可以立刻接管这些号
    stop_pidfile worker
    stop_pidfile api
    ;;
  status)
    for name in api worker; do
      if [ -f "$RUN/$name.pid" ] && kill -0 "$(cat "$RUN/$name.pid")" 2>/dev/null; then
        echo "$name: 运行中 (pid $(cat "$RUN/$name.pid"))"
      else
        echo "$name: 未运行"
      fi
    done
    probe "http://127.0.0.1:$API_PORT/health" || echo "（api /health 不可达）"; echo
    probe "http://127.0.0.1:$API_PORT/ready" || echo "（api /ready 不可达）"; echo
    probe "http://127.0.0.1:$WORKER_METRICS_PORT/metrics" | grep -E '^tgcc_' | head -12 \
      || echo "（worker /metrics 不可达）"
    ;;
  logs)
    tail -f "$RUN/api.log" "$RUN/worker.log"
    ;;
  *)
    echo "用法：$0 {up|down|status|logs}" >&2; exit 2
    ;;
esac
