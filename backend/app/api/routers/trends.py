"""趋势数据：`GET /api/metrics/trends?window=24h|7d|30d`。

数据来自 `metrics_samples`（小时级采样表，见 `api.sampler`）：
- `24h` → 逐小时（最多 24 个点）；
- `7d` / `30d` → 逐天（在线 / 异常取当天采样均值，任务成败取当天合计）。

口径说明：采样是**全局**的（一张表存系统整体负载），只包含数量，不含任何账号明细
（没有手机号 / 用户名 / 会话内容）。dashboard 上的数字对 operator 是按分配范围收敛的，
这里为了能画出连续曲线用的是全局计数，这一点写在 API_CONTRACT 里。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.api.routers import utcnow
from app.core import samples
from app.models import User
from app.schemas import TrendBucket, TrendPoint, TrendSeries, TrendsResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metrics", tags=["metrics"])

#: 四条曲线的展示定义（顺序即前端图例顺序）
SERIES_DEFS = (
    ("online_accounts", "在线账号"),
    ("abnormal_accounts", "异常账号"),
    ("tasks_succeeded", "任务成功"),
    ("tasks_failed", "任务失败"),
)


@router.get("/trends", response_model=TrendsResponse, summary="趋势（在线 / 异常 / 任务成败）")
async def metrics_trends(
    window: Optional[str] = Query(default=None, description="24h | 7d | 30d，默认 24h"),
    range: Optional[str] = Query(default=None, description="window 的别名（前端命名）"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TrendsResponse:
    """返回 `series`（画折线用）与 `points`（表格用）两份等价数据。

    采样协程每分钟写一次当前小时的桶；API 刚启动、还没到第一次采样时
    `latest_sample_at` 为 null、`series[].points` 为空数组，前端显示空状态即可。
    """
    key = (window or range or "24h").strip().lower()
    if key not in samples.TREND_WINDOWS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"window 只能是 {' / '.join(samples.supported_windows())}",
        )

    data = await samples.load_trends(session, window=key)
    rows = data["rows"]

    series = [
        TrendSeries(
            key=field,
            label=label,
            unit="count",
            points=[TrendPoint(t=row["bucket"], v=row[field]) for row in rows],
        )
        for field, label in SERIES_DEFS
    ]
    points = [
        TrendBucket(
            bucket=row["bucket"],
            online_accounts=row["online_accounts"],
            abnormal_accounts=row["abnormal_accounts"],
            tasks_succeeded=row["tasks_succeeded"],
            tasks_failed=row["tasks_failed"],
        )
        for row in rows
    ]

    return TrendsResponse(
        window=key,
        range=key,
        granularity=data["granularity"],
        from_=data["start"],
        to=data["end"],
        latest_sample_at=data["latest_sample_at"],
        generated_at=utcnow(),
        series=series,
        points=points,
    )
