"""趋势 schema：给控制台折线图用的时间序列。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class TrendPoint(BaseModel):
    """一个数据点。`t` 是整点（granularity=hour）或当天 00:00（granularity=day）。"""

    t: datetime
    v: float = 0


class TrendSeries(BaseModel):
    """一条曲线；前端按 key 画折线，label 直接当图例。"""

    key: str
    label: str
    unit: str = "count"
    points: List[TrendPoint] = Field(default_factory=list)


class TrendBucket(BaseModel):
    """扁平版：一行一个时间桶，适合表格视图或 CSV。"""

    bucket: datetime
    online_accounts: int = 0
    abnormal_accounts: int = 0
    tasks_succeeded: int = 0
    tasks_failed: int = 0


class TrendsResponse(BaseModel):
    """`window`/`range` 都接受（值：24h | 7d | 30d），24h 逐小时，7d/30d 逐天。"""

    model_config = ConfigDict(populate_by_name=True)

    window: str = "24h"
    range: str = "24h"
    granularity: str = Field(default="hour", description="hour | day")
    from_: Optional[datetime] = Field(default=None, alias="from")
    to: Optional[datetime] = None
    latest_sample_at: Optional[datetime] = Field(
        default=None, description="最近一次采样的时间；null 表示采样协程还没写过数据"
    )
    generated_at: Optional[datetime] = None
    series: List[TrendSeries] = Field(default_factory=list)
    points: List[TrendBucket] = Field(default_factory=list)
