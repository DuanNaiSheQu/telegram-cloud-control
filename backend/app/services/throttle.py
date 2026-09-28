"""节流与防封：养号阶梯、每日配额、动作间隔、活跃时段、FloodWait 熔断。

设计取向：**宁可少发，不要把号打废**。发送类任务在真正调用 Telegram 前先过这里，
不满足就直接顺延（`retry_after`），而不是硬发出去换一个 PeerFlood。

四道闸门（全部按「每个号」独立计算）：

1. **熔断**：`tg_accounts.flood_until` 未到期 → 立即拒绝，等熔断结束；
   连续吃到 FloodWait 会把额度打折（`risk_flags.downgrade`），并累加 `flood_strikes`。
2. **每日配额**：按号龄走养号阶梯（新号 20/天 → 老号配置上限），Redis 当日计数。
3. **动作间隔**：两次动作之间至少间隔 N 秒（号龄越大可以越短）。
4. **活跃时段**：默认只在本地 08:00–24:00 动作，避免凌晨批量操作这种典型机器特征。

风险动作加权：加群、群发这类动作按 `ACTION_COST` 折算成多个额度（默认 3 倍），
让「一天发 20 条私信」和「一天进 20 个群」的账号损耗不会一样。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from redis.asyncio import Redis

from app.config import settings
from app.models import TgAccount
from app.services.official import derive_throttle_overrides

logger = logging.getLogger(__name__)

#: Redis 计数键前缀：tgcc:throttle:<account_id>:<yyyymmdd>
THROTTLE_KEY = "tgcc:throttle:{account}:{day}"
#: 上次动作时间：用于最小间隔判断
LAST_ACTION_KEY = "tgcc:throttle:last:{account}"

#: 养号阶梯：(号龄下限天数, 每日上限, 最小间隔秒)。从下往上匹配第一个满足的档位
WARMUP_LADDER: tuple[tuple[int, int, int], ...] = (
    (0, 20, 120),    # 0-2 天：刚进来，只敢少量
    (3, 50, 60),     # 3-6 天
    (7, 80, 45),     # 7-13 天
    (14, 120, 30),   # 14-29 天
    (30, 200, 20),   # 30 天以上：老号，按配置上限
)

#: 动作权重：一条消息 = 1，加群/群发这类高风险动作更贵
ACTION_COST: dict[str, int] = {
    "send_message": 1,
    "bulk_pm": 1,
    "material_send": 1,
    "group_broadcast": 3,
    "storm_chat": 3,
    "persona_chat": 3,
    "join_group": 3,
    "force_add_member": 3,
}
#: 不加权重的类型（读取类）
COST_FREE_TYPES = {"sync_dialogs", "sync_messages", "account_check", "update_profile"}


@dataclass(slots=True)
class ThrottleDecision:
    """是否放行、为什么、多久后可以再试。"""

    ok: bool
    reason: str = ""
    retry_after: int = 0
    used: int = 0
    limit: int = 0
    cost: int = 1

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _local_now() -> datetime:
    return datetime.now()


def _day_key(moment: Optional[datetime] = None) -> str:
    return (moment or _now()).strftime("%Y%m%d")


def _seconds_until_next_day(moment: Optional[datetime] = None) -> int:
    now = moment or _now()
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(60, int((tomorrow - now).total_seconds()))


def account_age_days(account: TgAccount, *, now: Optional[datetime] = None) -> int:
    """号龄：优先养号起点，其次 Telegram 首次登录时间，最后建档时间。"""
    reference = getattr(account, "warmup_started_at", None) or getattr(account, "authorized_at", None) or getattr(
        account, "created_at", None
    )
    if reference is None:
        return 0
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return max(0, int(((now or _now()) - reference).total_seconds() // 86400))


def _ladder_entry(age_days: int) -> tuple[int, int]:
    chosen = WARMUP_LADDER[0]
    for entry in WARMUP_LADDER:
        if age_days >= entry[0]:
            chosen = entry
    return chosen[1], chosen[2]


def official_overrides(account: TgAccount, *, now: Optional[datetime] = None) -> dict[str, int]:
    """该号从服务端拿到的官方限制参数换算出的节流覆盖值（没同步过就是空）。"""
    limits = getattr(account, "official_limits", None) or {}
    if not limits:
        return {}
    base, interval = _ladder_entry(account_age_days(account, now=now))
    return derive_throttle_overrides(
        limits, base_daily=min(base, int(settings.throttle_daily_default)), base_interval=interval
    )


def daily_limit_for(account: TgAccount, *, now: Optional[datetime] = None) -> int:
    """每日额度：人工指定的优先；否则按养号阶梯，且不超过全局默认上限。"""
    explicit = int(getattr(account, "daily_message_limit", 0) or 0)
    if explicit > 0:
        return explicit
    base, _ = _ladder_entry(account_age_days(account, now=now))
    capped = min(base, int(settings.throttle_daily_default))
    # 熔断次数多 → 额度打折，逼着降速
    strikes = int(getattr(account, "flood_strikes", 0) or 0)
    if strikes >= 3:
        capped = max(5, capped // 2)
    # 官方参数只收紧：服务端要求更严时立刻跟上，放宽时不给我们松绑
    official = official_overrides(account, now=now)
    if official.get("daily_message_limit_max"):
        capped = min(capped, int(official["daily_message_limit_max"]))
    return max(5, capped)


def min_interval_for(account: TgAccount, *, now: Optional[datetime] = None) -> int:
    """动作最小间隔（秒）：人工指定优先，否则按阶梯。"""
    explicit = int(getattr(account, "min_action_seconds", 0) or 0)
    if explicit > 0:
        return explicit
    _, interval = _ladder_entry(account_age_days(account, now=now))
    official = official_overrides(account, now=now)
    if official.get("min_action_seconds"):
        interval = max(interval, int(official["min_action_seconds"]))
    return interval


def action_cost(task_type: str, *, explicit: Optional[int] = None) -> int:
    """这个动作算几个额度。"""
    if explicit is not None and explicit > 0:
        return explicit
    if task_type in COST_FREE_TYPES:
        return 0
    return ACTION_COST.get(task_type, 1)


def _active_window() -> tuple[int, int]:
    """解析活跃时段配置（形如 `8-24`），非法配置退回 0-24（全天）。"""
    raw = (settings.throttle_active_hours or "").strip()
    try:
        start_text, end_text = raw.split("-", 1)
        start, end = int(start_text), int(end_text)
        if 0 <= start <= 24 and 0 <= end <= 24 and start < end:
            return start, end
    except Exception:  # noqa: BLE001 - 配置写错不该让发送全挂
        pass
    return 0, 24


def _outside_active_window(now_local: datetime) -> Optional[int]:
    """不在活跃时段时返回「还有多少秒进入窗口」，在窗口内返回 None。"""
    start, end = _active_window()
    if start == 0 and end == 24:
        return None
    hour = now_local.hour
    if start <= hour < end:
        return None
    if hour < start:
        target = now_local.replace(hour=start, minute=0, second=0, microsecond=0)
    else:
        target = (now_local + timedelta(days=1)).replace(hour=start, minute=0, second=0, microsecond=0)
    return max(60, int((target - now_local).total_seconds()))


async def throttle_state(redis: Redis, account: TgAccount, *, now: Optional[datetime] = None) -> dict[str, Any]:
    """当前额度快照：给页面展示「今日已用 / 上限 / 熔断到什么时候」。"""
    moment = now or _now()
    key = THROTTLE_KEY.format(account=account.id, day=_day_key(moment))
    used = 0
    last_action_at: Optional[str] = None
    try:
        raw = await redis.get(key)
        used = int(raw or 0)
        last_action_at = await redis.get(LAST_ACTION_KEY.format(account=account.id))
    except Exception:  # noqa: BLE001 - Redis 抖动不影响事实，按未使用处理
        logger.debug("读取节流计数失败 account_id=%s", account.id)
    flood_until = getattr(account, "flood_until", None)
    if flood_until is not None and flood_until.tzinfo is None:
        flood_until = flood_until.replace(tzinfo=timezone.utc)
    return {
        "official_limits": len(getattr(account, "official_limits", None) or {}),
        "official_synced_at": (
            getattr(account, "official_synced_at", None).isoformat()
            if getattr(account, "official_synced_at", None)
            else None
        ),
        "used_today": used,
        "daily_limit": daily_limit_for(account, now=moment),
        "min_interval_seconds": min_interval_for(account, now=moment),
        "age_days": account_age_days(account, now=moment),
        "flood_until": flood_until.isoformat() if flood_until else None,
        "flood_strikes": int(getattr(account, "flood_strikes", 0) or 0),
        "last_action_at": last_action_at if isinstance(last_action_at, str) else None,
        "active_hours": settings.throttle_active_hours,
    }


async def allow_action(
    redis: Redis,
    account: TgAccount,
    *,
    task_type: str = "send_message",
    cost: Optional[int] = None,
    now: Optional[datetime] = None,
) -> ThrottleDecision:
    """发送前的四道闸门检查。不通过时 `retry_after` 就是建议顺延的秒数。"""
    moment = now or _now()
    limit = daily_limit_for(account, now=moment)
    weight = action_cost(task_type, explicit=cost)
    if weight == 0:
        return ThrottleDecision(ok=True, used=0, limit=limit, cost=0)

    # 1) 熔断
    flood_until = getattr(account, "flood_until", None)
    if flood_until is not None:
        if flood_until.tzinfo is None:
            flood_until = flood_until.replace(tzinfo=timezone.utc)
        if flood_until > moment:
            wait = int((flood_until - moment).total_seconds()) + 1
            return ThrottleDecision(
                ok=False,
                reason=f"该号被 Telegram 限流，熔断到 {flood_until.astimezone().strftime('%H:%M:%S')}",
                retry_after=wait,
                limit=limit,
                cost=weight,
            )

    # 2) 活跃时段
    wait_window = _outside_active_window(_local_now())
    if wait_window is not None:
        return ThrottleDecision(
            ok=False,
            reason=f"不在活跃时段（{settings.throttle_active_hours} 点），避开凌晨批量操作",
            retry_after=wait_window,
            limit=limit,
            cost=weight,
        )

    # 3) 最小间隔
    interval = min_interval_for(account, now=moment)
    try:
        last_raw = await redis.get(LAST_ACTION_KEY.format(account=account.id))
    except Exception:  # noqa: BLE001
        last_raw = None
    if last_raw:
        try:
            last_at = datetime.fromisoformat(str(last_raw))
            if last_at.tzinfo is None:
                last_at = last_at.replace(tzinfo=timezone.utc)
            elapsed = (moment - last_at).total_seconds()
            if elapsed < interval:
                wait = int(interval - elapsed) + 1
                return ThrottleDecision(
                    ok=False,
                    reason=f"距上次动作仅 {int(elapsed)} 秒，间隔要求 {interval} 秒",
                    retry_after=wait,
                    limit=limit,
                    cost=weight,
                )
        except ValueError:
            pass

    # 4) 每日配额
    key = THROTTLE_KEY.format(account=account.id, day=_day_key(moment))
    try:
        used = int(await redis.get(key) or 0)
    except Exception:  # noqa: BLE001
        used = 0
    if used + weight > limit:
        return ThrottleDecision(
            ok=False,
            reason=f"今日额度已用 {used}/{limit}（这次动作需要 {weight}）",
            retry_after=_seconds_until_next_day(moment),
            used=used,
            limit=limit,
            cost=weight,
        )
    return ThrottleDecision(ok=True, used=used, limit=limit, cost=weight)


async def record_action(
    redis: Redis, account: TgAccount, *, cost: int, task_type: str = "", now: Optional[datetime] = None
) -> int:
    """记一次动作：累加当日额度并刷新最小间隔时间戳。返回今日累计用量。"""
    moment = now or _now()
    if cost <= 0:
        return 0
    key = THROTTLE_KEY.format(account=account.id, day=_day_key(moment))
    try:
        used = int(await redis.incrby(key, cost))
        await redis.expire(key, _seconds_until_next_day(moment))
        await redis.set(LAST_ACTION_KEY.format(account=account.id), moment.isoformat(), ex=86400)
    except Exception:  # noqa: BLE001 - 计数丢了只是少挡一次，不影响发送结果
        logger.warning("写入节流计数失败 account_id=%s type=%s", account.id, task_type)
        return 0
    logger.info(
        "节流计数 account_id=%s type=%s cost=%s 今日=%s/%s",
        account.id,
        task_type,
        cost,
        used,
        daily_limit_for(account, now=moment),
    )
    return used


async def note_flood(account: TgAccount, seconds: int, *, now: Optional[datetime] = None) -> None:
    """吃到 FloodWait：写熔断到期时间并累加次数（调用方负责 commit）。"""
    moment = now or _now()
    cooldown = max(5, int(seconds)) + max(0, int(settings.throttle_flood_cooldown_seconds))
    account.flood_until = moment + timedelta(seconds=cooldown)
    account.flood_strikes = int(getattr(account, "flood_strikes", 0) or 0) + 1
    flags = dict(getattr(account, "risk_flags", {}) or {})
    flags["last_flood_at"] = moment.isoformat()
    flags["flood_strikes"] = account.flood_strikes
    if account.flood_strikes >= 3:
        flags["downgrade"] = "连续限流，额度已自动减半"
    account.risk_flags = flags
    logger.warning(
        "账号被限流，已熔断 account_id=%s 冷却=%s 秒 strikes=%s", account.id, cooldown, account.flood_strikes
    )


__all__ = [
    "ACTION_COST",
    "COST_FREE_TYPES",
    "THROTTLE_KEY",
    "ThrottleDecision",
    "WARMUP_LADDER",
    "account_age_days",
    "official_overrides",
    "action_cost",
    "allow_action",
    "daily_limit_for",
    "min_interval_for",
    "note_flood",
    "record_action",
    "throttle_state",
]
