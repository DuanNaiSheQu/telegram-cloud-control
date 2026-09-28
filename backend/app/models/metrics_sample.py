"""按小时聚合的趋势采样：给控制台的折线图提供「在线号数 / 异常号数 / 任务成败」时间序列。

为什么单独建表而不是每次查历史：任务表只保留最终状态，账号表只有当前状态，
事后想画一条曲线就必须靠采样。写入口径：每小时一行（bucket 为主键），
每个 API 副本通过 Redis leader 键竞争采样权，同一个 bucket 用 UPSERT 覆盖 / 累加。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class MetricsSample(Base, TimestampMixin):
    """一小时一行。账号类字段是这一小时**最后一次采样**的快照，任务类字段是**区间累加**。"""

    __tablename__ = "metrics_samples"

    #: 整点（UTC），如 2026-09-28T13:00:00+00:00
    bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    total_accounts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    online_accounts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    abnormal_accounts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    #: 区间内完成 / 失败的任务数（采样协程按上次采样时间做增量累加）
    tasks_succeeded: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    tasks_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    #: 最近一次写入这个 bucket 的时间，页面用来判断曲线是否新鲜
    sampled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
