#!/usr/bin/env bash
# Telegram 云控 —— Postgres 备份脚本
#
# 两件事：
#   1) 每日逻辑备份：pg_dump -Fc        -> $BACKUP_DIR/daily-<UTC时间戳>.dump
#   2) 每周基础备份：pg_basebackup -Ft -z -X none -> $BACKUP_DIR/base-<UTC时间戳>.tar.gz
#      基础备份 + WAL 归档 = 按时间点恢复（WAL 由 postgres 的 archive_command 持续写进 pg_wal_archive 卷）。
#      ⚠️ base-*.tar.gz 单独不可恢复，必须连同 WAL 归档一起用，步骤见 deploy/postgres-backup.md。
#
# 用法：
#   deploy/backup.sh              # 等价于 all：先日备再周备（手动执行时用这个）
#   deploy/backup.sh daily        # 只做逻辑备份（cron 每天 03:10）
#   deploy/backup.sh base         # 只做基础备份（cron 每周日 03:40）
#   BACKUP_KIND=daily deploy/backup.sh
#   make backup
#
# 运行位置：宿主即可（默认 BACKUP_MODE=docker，借 docker compose exec 在容器里跑客户端）。
# 退出码：0=成功；1=备份失败（并向 pushgateway 上报 0）；2=参数错误；3=备份成功但上报失败。
#
# 成功/失败都会推送到 pushgateway（job=backup）：
#   tgcc_last_successful_backup_timestamp_seconds        每日备份最近成功时间（失败推 0）
#   tgcc_last_successful_basebackup_timestamp_seconds    周基础备份最近成功时间
#   tgcc_backup_duration_seconds / tgcc_backup_last_run_timestamp_seconds
# 告警规则见 deploy/alert.rules.yml（tgcc-database-backup 组）。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

# ---------------------------------------------------------------- 配置（都可用环境变量覆盖）

BACKUP_KIND="${1:-${BACKUP_KIND:-all}}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"
BACKUP_MODE="${BACKUP_MODE:-docker}"                 # docker | direct
BACKUP_KEEP_DAILY="${BACKUP_KEEP_DAILY:-7}"          # 保留几个日备
BACKUP_KEEP_WEEKLY="${BACKUP_KEEP_WEEKLY:-4}"        # 保留几个周备
BACKUP_COMPOSE_SERVICE="${BACKUP_COMPOSE_SERVICE:-postgres}"
BACKUP_TIMEOUT_SECONDS="${BACKUP_TIMEOUT_SECONDS:-3600}"
PGUSER="${PGUSER:-${POSTGRES_USER:-cloudctl}}"
PGDATABASE="${PGDATABASE:-${POSTGRES_DB:-cloudctl}}"

COMPOSE_BIN="${COMPOSE_BIN:-docker compose}"
read -r -a _compose_bin <<< "$COMPOSE_BIN"
COMPOSE=("${_compose_bin[@]}" -f "$PROJECT_DIR/docker-compose.yml" --project-directory "$PROJECT_DIR")

TS="$(date -u +%Y%m%dT%H%M%SZ)"
START_EPOCH="$(date +%s)"

# ---------------------------------------------------------------- 日志（中文，带时间戳）

log() { printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
warn() { printf '[%s] 警告：%s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2; }
err() { printf '[%s] 错误：%s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2; }

# ---------------------------------------------------------------- 上报 pushgateway

# 候选地址：显式配置 > 容器网络内服务名 > 宿主已发布端口
pushgateway_candidates() {
  if [ -n "${BACKUP_PUSHGATEWAY_URL:-}" ]; then
    printf '%s\n' "${BACKUP_PUSHGATEWAY_URL%/}"
    return 0
  fi
  printf '%s\n' "http://pushgateway:9091"
  printf '%s\n' "http://127.0.0.1:${PUSHGATEWAY_PORT:-9091}"
}

# push_metrics <group> <指标文本>
push_metrics() {
  local group="$1" body="$2" base
  while IFS= read -r base; do
    [ -n "$base" ] || continue
    if printf '%s\n' "$body" | curl -fsS --max-time 10 --data-binary @- "$base/metrics/job/backup/kind/$group" >/dev/null 2>&1; then
      log "已上报备份指标到 ${base}（${group}）"
      return 0
    fi
  done < <(pushgateway_candidates)
  return 1
}

report_success() {
  local kind="$1" metric="$2" ts="$3" duration="$4"
  local body
  body="# TYPE $metric gauge
$metric $ts
# TYPE tgcc_backup_duration_seconds gauge
tgcc_backup_duration_seconds $duration
# TYPE tgcc_backup_last_run_timestamp_seconds gauge
tgcc_backup_last_run_timestamp_seconds $ts"
  push_metrics "$kind" "$body" || return 1
}

# 失败时推 0：即使备份没成功，也要让「最近成功时间」这一类告警看见 0
report_failure() {
  local kind="$1" metric="$2"
  local body="# TYPE $metric gauge
$metric 0
# TYPE tgcc_backup_last_run_timestamp_seconds gauge
tgcc_backup_last_run_timestamp_seconds $(date +%s)"
  push_metrics "$kind" "$body" || warn "上报失败状态到 pushgateway 也没成功：pushgateway 是否在跑（make monitoring）？"
}

# ---------------------------------------------------------------- 备份执行

pg_dump_to() {
  local target="$1"
  if [ "$BACKUP_MODE" = "docker" ]; then
    "${COMPOSE[@]}" exec -T "$BACKUP_COMPOSE_SERVICE" \
      pg_dump -Fc -U "$PGUSER" -d "$PGDATABASE" > "$target"
  else
    pg_dump -Fc -h "${PGHOST:-127.0.0.1}" -p "${PGPORT:-5432}" -U "$PGUSER" -d "$PGDATABASE" > "$target"
  fi
}

pg_basebackup_to() {
  local target="$1"
  # -Ft tar 格式、-z gzip、-D - 写到 stdout（只有 tar 格式允许）、-X none 不往备份里塞 WAL。
  #
  # 为什么用 -X none：pg_basebackup 不允许「tar 格式 + stdout + -X stream/fetch」——
  # 实测报错 cannot stream write-ahead logs in tar mode to stdout；而 -Fp 到 stdout 会
  # 静默产出 0 字节文件（已实测，run_backup 里的 -s 检查能挡住）。要自带 WAL 就得写出到
  # 目录，代价是容器内属主与额外挂载，所以这里选 -X none：
  #   base-*.tar.gz（基础备份）+ Postgres 持续写入的 WAL 归档（archive_mode=on，
  #   archive_command 落到 pg_wal_archive 卷）= 按时间点恢复的完整链条。
  # 代价与前提：base-*.tar.gz 单独不能恢复，必须连同 WAL 归档一起用；恢复步骤见
  # deploy/postgres-backup.md，do_base 里也会检查 archive_mode。
  if [ "$BACKUP_MODE" = "docker" ]; then
    "${COMPOSE[@]}" exec -T "$BACKUP_COMPOSE_SERVICE" \
      pg_basebackup -D - -Ft -z -X none -c fast -U "$PGUSER" > "$target"
  else
    pg_basebackup -D - -Ft -z -X none -c fast \
      -h "${PGHOST:-127.0.0.1}" -p "${PGPORT:-5432}" -U "$PGUSER" > "$target"
  fi
}

# 一条 SQL：给 archive_mode 之类的检查用
psql_query() {
  local sql="$1"
  if [ "$BACKUP_MODE" = "docker" ]; then
    "${COMPOSE[@]}" exec -T "$BACKUP_COMPOSE_SERVICE" \
      psql -U "$PGUSER" -d "$PGDATABASE" -tAc "$sql"
  else
    psql -h "${PGHOST:-127.0.0.1}" -p "${PGPORT:-5432}" -U "$PGUSER" -d "$PGDATABASE" -tAc "$sql"
  fi
}

# 基础备份只有在 archive_mode=on 时才能用于按时间点恢复，动手前先确认
check_archive_mode() {
  local mode
  if [ "$BACKUP_MODE" != "docker" ] && ! command -v psql >/dev/null 2>&1; then
    warn "宿主没有 psql，跳过 archive_mode 检查"
    return 0
  fi
  mode="$(psql_query 'SHOW archive_mode' 2>/dev/null | tr -d '[:space:]')" || mode=""
  case "$mode" in
    on)
      log "archive_mode=on：WAL 归档在写，基础备份 + 归档可做按时间点恢复"
      ;;
    "")
      warn "读不到 archive_mode（psql 不可用或连不上），无法确认按时间点恢复是否可用"
      ;;
    *)
      warn "archive_mode=${mode}：这个基础备份无法用于按时间点恢复！检查 postgres 启动参数（wal_level=replica / archive_mode=on / archive_command）"
      ;;
  esac
}

# 写 .part 再改名：半截文件不会被当成可恢复的备份，也不参与保留份数统计
run_with_timeout() {
  # macOS 没有 timeout，有 coreutils 的话是 gtimeout；都没有就退化为不设超时
  if command -v timeout >/dev/null 2>&1; then
    timeout "$BACKUP_TIMEOUT_SECONDS" "$@"
  elif command -v gtimeout >/dev/null 2>&1; then
    gtimeout "$BACKUP_TIMEOUT_SECONDS" "$@"
  else
    warn "找不到 timeout / gtimeout，本次不做超时保护"
    "$@"
  fi
}

run_backup() {
  local kind="$1" target="$2" runner="$3"
  log "开始${kind}备份 -> $target"
  rm -f "$target.part"
  if ! run_with_timeout "$runner" "$target.part"; then
    rm -f "$target.part"
    err "${kind}备份失败（命令非 0 退出或超过 ${BACKUP_TIMEOUT_SECONDS} 秒）"
    return 1
  fi
  if [ ! -s "$target.part" ]; then
    rm -f "$target.part"
    err "${kind}备份失败：输出为空（连接串、权限或 PGUSER/PGDATABASE 是否正确？）"
    return 1
  fi
  mv "$target.part" "$target"
  log "${kind}备份完成：${target}（$(du -h "$target" | cut -f1)）"
}

do_daily() {
  local target="$BACKUP_DIR/daily-$TS.dump" start now
  start="$(date +%s)"
  run_backup "每日逻辑" "$target" pg_dump_to || return 1
  now="$(date +%s)"
  log "每日备份耗时 $((now - start)) 秒"
  FAILED_KIND=""
  if report_success daily tgcc_last_successful_backup_timestamp_seconds "$now" "$((now - start))"; then
    return 0
  fi
  REPORT_FAILED=1
  return 0
}

do_base() {
  local target="$BACKUP_DIR/base-$TS.tar.gz" start now
  start="$(date +%s)"
  check_archive_mode
  run_backup "每周基础" "$target" pg_basebackup_to || return 1
  now="$(date +%s)"
  log "基础备份耗时 $((now - start)) 秒"
  FAILED_KIND=""
  if report_success base tgcc_last_successful_basebackup_timestamp_seconds "$now" "$((now - start))"; then
    return 0
  fi
  REPORT_FAILED=1
  return 0
}

# ---------------------------------------------------------------- 保留份数

prune_kind() {
  local label="$1" pattern="$2" keep="$3" old
  if ! [ "$keep" -ge 1 ] 2>/dev/null; then
    warn "保留份数配置非法（${label}：${keep}），跳过清理"
    return 0
  fi
  old="$(ls -1t "$BACKUP_DIR"/$pattern 2>/dev/null | tail -n +"$((keep + 1))" || true)"
  if [ -z "$old" ]; then
    log "${label}保留 $keep 份，无需清理"
    return 0
  fi
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    rm -f "$f"
    log "删除超期${label}：$f"
  done <<< "$old"
}

prune() {
  prune_kind "日备" "daily-*.dump" "$BACKUP_KEEP_DAILY"
  prune_kind "周备" "base-*.tar.gz" "$BACKUP_KEEP_WEEKLY"
}

# ---------------------------------------------------------------- 主流程

REPORT_FAILED=0
FAILED_KIND=""

on_error() {
  local line="$1"
  trap - ERR
  err "备份脚本中断（第 $line 行）"
  if [ -n "$FAILED_KIND" ]; then
    case "$FAILED_KIND" in
      daily) report_failure daily tgcc_last_successful_backup_timestamp_seconds ;;
      base) report_failure base tgcc_last_successful_basebackup_timestamp_seconds ;;
    esac
  fi
  exit 1
}
trap 'on_error $LINENO' ERR

usage() {
  cat <<'USAGE'
用法：deploy/backup.sh [daily|base|all]

  daily   只做每日逻辑备份（pg_dump -Fc）
  base    只做每周基础备份（pg_basebackup -Ft -z，支撑按时间点恢复）
  all     两个都做（默认，手动执行时用）

常用环境变量：
  BACKUP_MODE=docker|direct   默认 docker（借 docker compose exec 在容器内跑客户端）
  BACKUP_DIR=./backups        备份落盘目录
  BACKUP_KEEP_DAILY=7         保留几个日备
  BACKUP_KEEP_WEEKLY=4        保留几个周备
  BACKUP_PUSHGATEWAY_URL=...  上报地址；留空按「服务名 -> 宿主端口」顺序自动尝试
  PGHOST/PGPORT/PGUSER/PGPASSWORD   direct 模式直连参数
USAGE
}

main() {
  case "$BACKUP_KIND" in
    daily|base|all) ;;
    -h|--help|help) usage; exit 0 ;;
    *) err "未知的备份类型：${BACKUP_KIND}（只支持 daily / base / all）"; usage >&2; exit 2 ;;
  esac

  log "===== Telegram 云控备份开始（类型 ${BACKUP_KIND}，模式 ${BACKUP_MODE}，时间戳 ${TS}）====="
  command -v curl >/dev/null 2>&1 || warn "找不到 curl，备份指标无法上报"
  mkdir -p "$BACKUP_DIR"

  case "$BACKUP_KIND" in
    daily)
      FAILED_KIND=daily
      do_daily || { report_failure daily tgcc_last_successful_backup_timestamp_seconds; err "每日备份失败，已上报 0"; exit 1; }
      ;;
    base)
      FAILED_KIND=base
      do_base || { report_failure base tgcc_last_successful_basebackup_timestamp_seconds; err "基础备份失败，已上报 0"; exit 1; }
      ;;
    all)
      FAILED_KIND=daily
      do_daily || { report_failure daily tgcc_last_successful_backup_timestamp_seconds; err "每日备份失败，已上报 0"; exit 1; }
      FAILED_KIND=base
      do_base || { report_failure base tgcc_last_successful_basebackup_timestamp_seconds; err "基础备份失败，已上报 0"; exit 1; }
      ;;
  esac
  FAILED_KIND=""

  prune

  log "当前备份文件："
  ls -1t "$BACKUP_DIR"/daily-*.dump "$BACKUP_DIR"/base-*.tar.gz 2>/dev/null | head -n 20 || true

  log "===== 备份结束，总耗时 $(( $(date +%s) - START_EPOCH )) 秒 ====="
  if [ "$REPORT_FAILED" = "1" ]; then
    err "备份本身成功，但指标上报失败：pushgateway 是否在跑？BACKUP_PUSHGATEWAY_URL 是否正确？"
    exit 3
  fi
  exit 0
}

main "$@"
