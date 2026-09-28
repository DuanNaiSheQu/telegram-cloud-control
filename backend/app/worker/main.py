"""Worker 进程入口：`python -m app.worker.main`。

顺序：JSON 日志 → Prometheus /metrics → 构造 Worker → 装 SIGTERM/SIGINT → 事件循环。
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from app.config import settings
from app.logging_conf import setup_logging
from app.worker.metrics import start_metrics_server
from app.worker.worker import Worker

logger = logging.getLogger("app.worker.main")


def _install_signal_handlers(worker: Worker) -> None:
    """SIGTERM / SIGINT → 只置退出标志；不支持 add_signal_handler 时退回 signal.signal。"""
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, worker.request_stop)
        except (NotImplementedError, RuntimeError):  # pragma: no cover - 非主流平台
            signal.signal(sig, lambda *_: worker.request_stop())


async def _run_worker() -> int:
    """跑 Worker；不管怎么退出都要走优雅退出（释放租约）。"""
    worker = Worker()
    _install_signal_handlers(worker)
    logger.info(
        "Worker 进程启动",
        extra={"worker_id": worker.worker_id, "telegram_ready": worker.telegram_ready},
    )
    try:
        await worker.run_forever()
    finally:
        await worker.stop()
    return 0


def main() -> int:
    """进程入口：返回退出码（0 正常，1 未捕获异常）。"""
    setup_logging("worker", settings.log_level)
    start_metrics_server(settings.worker_metrics_port)
    try:
        return asyncio.run(_run_worker())
    except KeyboardInterrupt:  # pragma: no cover - 手动 Ctrl+C
        logger.info("收到 KeyboardInterrupt，退出")
        return 130
    except Exception:  # noqa: BLE001 - 顶层异常要留在日志里，不吞
        logger.exception("Worker 未捕获异常，退出")
        return 1


if __name__ == "__main__":
    sys.exit(main())
