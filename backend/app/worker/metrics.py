"""Prometheus 指标：Worker 单独暴露 `:9101/metrics`（在线号、重连、任务成败、租约续期失败）。

指标名统一 `tgcc_` 前缀，和 `规划.md`「运维」一节列的四类告警对齐。
本模块不依赖任何业务代码，Worker 用 `record_*` / `set_*` 小函数打点。
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    start_http_server,
)

from app.models import ACCOUNT_STATUS_LABELS

logger = logging.getLogger(__name__)

#: Worker 用自己的 registry，不用默认 registry。
#: 原因：API 侧（app/api/metrics.py）也有 tgcc_tasks 系列指标，两者装进同一个进程
#: （测试脚本、或将来把 Wheel 打进同一个进程）时默认 registry 会因家族重名直接抛错。
#: 分开 registry 后，`import app.api.main` 与 `import app.worker.main` 可以共存。
REGISTRY = CollectorRegistry()

# ---------- 指标定义 ----------

ONLINE_ACCOUNTS = Gauge(
    "tgcc_online_accounts",
    "本 Worker 当前保持可用连接的用户号数量",
    registry=REGISTRY,
)

LEASED_ACCOUNTS = Gauge(
    "tgcc_leased_accounts",
    "本 Worker 当前持有的账号租约数量",
    registry=REGISTRY,
)

RECONNECTS_TOTAL = Counter(
    "tgcc_reconnects_total",
    "用户号连接重试次数（含首次建连失败后的每一次重连）",
    registry=REGISTRY,
)

TASKS_TOTAL = Counter(
    "tgcc_tasks_total",
    "任务执行计数",
    ["type", "outcome"],
    registry=REGISTRY,
)

TASK_DURATION_SECONDS = Histogram(
    "tgcc_task_duration_seconds",
    "任务执行耗时（秒）",
    ["type"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300),
    registry=REGISTRY,
)

LEASE_RENEW_FAILURES_TOTAL = Counter(
    "tgcc_lease_renew_failures_total",
    "租约续期失败次数（续不上会有别的副本接管该号）",
    registry=REGISTRY,
)

ACCOUNT_STATUS = Gauge(
    "tgcc_account_status",
    "各状态账号数量（全库，按 tg_accounts.status 分组）",
    ["status"],
    registry=REGISTRY,
)

WORKER_HEARTBEAT_AGE_SECONDS = Gauge(
    "tgcc_worker_heartbeat_age_seconds",
    "本 Worker 最近一次写心跳距今的秒数",
    registry=REGISTRY,
)

WORKER_INFO = Gauge(
    "tgcc_worker_info",
    "Worker 身份（值恒为 1，worker_id 在标签上），便于告警 / Grafana 直接指出是哪个副本",
    ["worker_id"],
    registry=REGISTRY,
)

#: 本进程设过的 worker_id 标签，换 id 时把旧标签清掉，避免出现两个「在跑」的副本
_info_worker_ids: set = set()

# 已知状态先建好标签，避免页面里出现「无数据」的空档
for _status in ACCOUNT_STATUS_LABELS:
    ACCOUNT_STATUS.labels(status=_status).set(0)

#: 任务结果取值：ok=成功，failed=彻底失败，retried=失败但回到队列
TASK_OUTCOMES = ("ok", "failed", "retried")


def start_metrics_server(port: int) -> bool:
    """在后台线程启动 /metrics HTTP 服务；端口被占用时只告警不致命。"""
    try:
        start_http_server(port, registry=REGISTRY)
    except OSError as exc:
        logger.error(
            "Prometheus /metrics 端口启动失败，指标不可采集",
            extra={"component": "worker", "metrics_port": port, "error": str(exc)},
        )
        return False
    logger.info(
        "Prometheus 指标已暴露",
        extra={"component": "worker", "metrics_port": port, "path": "/metrics"},
    )
    return True


def set_online_accounts(count: int) -> None:
    """在线号数量。"""
    ONLINE_ACCOUNTS.set(max(0, int(count)))


def set_leased_accounts(count: int) -> None:
    """持有租约数量。"""
    LEASED_ACCOUNTS.set(max(0, int(count)))


def record_reconnect() -> None:
    """记一次重连尝试。"""
    RECONNECTS_TOTAL.inc()


def record_task(task_type: str, ok: bool, duration: float, outcome: Optional[str] = None) -> None:
    """记一次任务执行：耗时直方图 + 成败计数。"""
    kind = task_type or "unknown"
    result = outcome or ("ok" if ok else "failed")
    if result not in TASK_OUTCOMES:  # 防御：外部传了不认识的取值
        result = "failed" if not ok else "ok"
    TASKS_TOTAL.labels(type=kind, outcome=result).inc()
    TASK_DURATION_SECONDS.labels(type=kind).observe(max(0.0, float(duration)))


def record_task_skipped(task_type: str) -> None:
    """记一次「领到了但跳过」的任务，不算成功也不算失败。"""
    TASKS_TOTAL.labels(type=task_type or "unknown", outcome="skipped").inc()


def record_lease_renew_failure() -> None:
    """记一次租约续期失败。"""
    LEASE_RENEW_FAILURES_TOTAL.inc()


def set_account_status_counts(counts: Dict[str, int]) -> None:
    """按状态写账号数量；未出现的状态归零。"""
    for status, label in ACCOUNT_STATUS_LABELS.items():
        ACCOUNT_STATUS.labels(status=status).set(int(counts.get(status, 0)))


def set_worker_heartbeat_age(seconds: float) -> None:
    """本进程心跳年龄；正常应远小于 60 秒。"""
    WORKER_HEARTBEAT_AGE_SECONDS.set(max(0.0, float(seconds)))


def set_worker_info(worker_id: str) -> None:
    """暴露本副本身份，告警正文里能直接写出 worker_id（不用再 docker inspect 反查）。"""
    label = worker_id or "unknown"
    for stale in _info_worker_ids - {label}:
        try:
            WORKER_INFO.remove(stale)
        except KeyError:  # 该标签本轮没出现过
            pass
    _info_worker_ids.add(label)
    WORKER_INFO.labels(worker_id=label).set(1)


__all__ = [
    "TASK_OUTCOMES",
    "record_lease_renew_failure",
    "record_reconnect",
    "record_task",
    "record_task_skipped",
    "set_account_status_counts",
    "set_leased_accounts",
    "set_online_accounts",
    "set_worker_heartbeat_age",
    "set_worker_info",
    "start_metrics_server",
]
