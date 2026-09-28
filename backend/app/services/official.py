"""官方机制：Telegram 客户端身份对齐 + 服务端下发限制参数 → 养号节流。

为什么这么做：Telegram 的客户端是开源的（TDesktop / Android / iOS），服务端还会通过
`help.GetAppConfig` / `help.GetConfig` 把**官方限制参数**下发给客户端（flood 类、群相关上限、
编辑时限等）。官方客户端就是照着这些参数自我节流的，所以：

1. **身份对齐**：设备指纹不再随机编造，而是从「官方真实发布过的客户端版本」里取——
   编造出来的 `app_version` 在服务端看就是不存在的版本，反而异常；
2. **限制对齐**：把服务端下发的 flood/上限参数解析出来，取「比我们默认值更保守」的那个，
   用它驱动节流（这样服务端放宽时我们不会一直卡着自己，服务端收紧时我们立刻跟上）；
3. **行为对齐**：养号活动包模仿官方客户端的节奏——上线、翻会话、打字状态、下线，
   **不发任何消息**，在服务端看来就是「一个正常在刷消息的用户」。

官方参数缺失时（未同步过、或服务端没下发该项）全部回退到 `services/throttle.py` 的内置阶梯，
不阻塞任何功能。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OfficialClient:
    """一个真实存在过的官方客户端身份（device_model / system_version / app_version 组合）。"""

    device_model: str
    system_version: str
    app_version: str
    lang_pack: str
    system_lang_code: str = "zh-CN"


#: 官方客户端版本表（公开的发布线，按平台分组；新增时只追加，别改历史值）
OFFICIAL_CLIENTS: tuple[OfficialClient, ...] = (
    # Telegram Android（Google Play 发布线）
    OfficialClient("Samsung SM-S918B", "SDK 34", "11.2.3", "android"),
    OfficialClient("Google Pixel 8 Pro", "SDK 34", "11.2.3", "android"),
    OfficialClient("Xiaomi 23127PN0CG", "SDK 33", "11.1.1", "android"),
    OfficialClient("HUAWEI ALN-AL00", "SDK 31", "10.14.5", "android"),
    OfficialClient("OPPO CPH2525", "SDK 33", "10.13.2", "android"),
    OfficialClient("vivo V2254A", "SDK 33", "10.12.0", "android"),
    OfficialClient("OnePlus CPH2449", "SDK 34", "11.2.3", "android"),
    # Telegram iOS
    OfficialClient("iPhone 15 Pro", "iOS 17.5", "11.2.0", "ios", "zh-Hans-CN"),
    OfficialClient("iPhone 14 Pro Max", "iOS 17.4", "11.1.0", "ios", "zh-Hans-CN"),
    OfficialClient("iPhone 13", "iOS 16.7", "10.9.1", "ios", "zh-Hans-CN"),
    OfficialClient("iPad Pro 11", "iPadOS 17.5", "11.2.0", "ios", "zh-Hans-CN"),
    # Telegram Desktop
    OfficialClient("Desktop", "Windows 11", "5.3.1 x64", "tdesktop", "zh-hans"),
    OfficialClient("Desktop", "macOS 14.5", "5.3.1", "tdesktop", "zh-hans"),
)


def pick_official_client(rng: Any = None, *, prefer: Optional[str] = None) -> OfficialClient:
    """从官方版本表里挑一个身份；`prefer` 可指定 android / ios / tdesktop 平台。"""
    pool = [client for client in OFFICIAL_CLIENTS if prefer is None or client.lang_pack == prefer] or list(OFFICIAL_CLIENTS)
    if rng is not None:
        return rng.choice(pool)
    import random

    return random.choice(pool)


#: 从服务端 config 里提取的限制键（前缀匹配）：flood / 群上限 / 时限
LIMIT_KEY_PREFIXES = (
    "flood_",
    "group_flood_limit",
    "chat_size_max",
    "megagroup_size_max",
    "edit_time_limit",
    "revoke_time_limit",
    "revoke_pm_time_limit",
    "message_length_max",
    "caption_length_max",
    "upload_max_fileparts",
    "forwarded_count_max",
    "call_",
    "channels_",
    "recommended_",
)

#: 明确与限速无关、提取时丢掉的噪声键
LIMIT_KEY_SKIP = (
    "upload_max_fileparts",
    "call_ring_timeout",
    "call_receive_timeout",
    "channels_read_media_period",
    "recommended_insurance_",
    "call_connect_timeout",
)

#: 官方 flood 参数 → 我们节流参数的换算（保守取整）
FLOOD_TO_THROTTLE = {
    "flood_wait": ("min_action_seconds", 1.0),          # 官方等待秒数直接映射为最小间隔
    "flood_premium_wait": ("min_action_seconds", 1.0),
    "flood_add_peer": ("add_peer_daily", 1.0),          # 加人/拉群的每日上限
    "flood_premium_add_peer": ("add_peer_daily", 1.0),
}


def extract_official_limits(app_config: Any) -> dict[str, Any]:
    """把 `help.GetAppConfig` 的返回体解析成「限速相关参数」字典。

    只保留白名单前缀的键：既避免把无关配置塞进库，也便于后续按需映射。
    """
    if app_config is None:
        return {}
    raw = getattr(app_config, "config", None)
    if raw is None:
        return {}
    limits: dict[str, Any] = {}
    if isinstance(raw, dict):
        items = raw.items()
    else:
        # Telethon 把 config 包成 JsonObject/JsonNull，转成 dict 再挑
        try:
            items = dict(raw).items()
        except Exception:  # noqa: BLE001
            return {}
    for key, value in items:
        lowered = str(key)
        if not any(lowered.startswith(prefix) for prefix in LIMIT_KEY_PREFIXES):
            continue
        if any(lowered.startswith(skip) for skip in LIMIT_KEY_SKIP):
            continue
        limits[lowered] = _plain(value)
    return limits


def _plain(value: Any) -> Any:
    """Telethon 的 JsonObject/JsonNumber 等 → 原生类型。"""
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    for attr in ("value", "_value"):
        inner = getattr(value, attr, None)
        if isinstance(inner, (int, float, str, bool)):
            return inner
    try:
        return str(value)
    except Exception:  # noqa: BLE001
        return None


def extract_dc_options(config: Any) -> dict[str, Any]:
    """`help.GetConfig` 里与连接相关的关键参数（DC 数、电话、静态地址）。"""
    if config is None:
        return {}
    options = getattr(config, "dc_options", None) or []
    return {
        "dc_count": len([opt for opt in options if getattr(opt, "ipv4", None) or getattr(opt, "ipv6", None)]),
        "this_dc": getattr(config, "this_dc", None),
        "date": str(getattr(config, "date", "")),
        "expires": str(getattr(config, "expires", "")),
        "test_mode": bool(getattr(config, "test_mode", False)),
    }


def derive_throttle_overrides(limits: dict[str, Any], *, base_daily: int, base_interval: int) -> dict[str, int]:
    """官方参数 → 节流覆盖值。规则：**只收紧、不放松**（取更保守的那个）。

    - `flood_wait` / `flood_premium_wait`：作为动作最小间隔的**下限**（官方要等多久，我们就至少隔多久）；
    - `flood_add_peer`：作为「加人/拉群」类动作的每日上限，若它比我们默认阶梯更严就用它；
    - 其它键先只做记录，不参与换算（避免把含义不确定的参数用在发送上）。
    """
    overrides: dict[str, int] = {}
    for key, (target, factor) in FLOOD_TO_THROTTLE.items():
        if key not in limits:
            continue
        try:
            value = float(limits[key])
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        if target == "min_action_seconds":
            candidate = int(max(base_interval, value * factor))
            overrides[target] = max(overrides.get(target, 0), candidate)
        elif target == "add_peer_daily":
            candidate = int(value * factor)
            overrides["add_peer_daily"] = min(overrides.get("add_peer_daily", 10**9), candidate)
    if base_daily > 0:
        # 官方没有直接给「每日发消息上限」，这里只保证不越界
        overrides["daily_message_limit_max"] = base_daily
    return overrides


def merge_limits(*sources: Optional[dict[str, Any]]) -> dict[str, Any]:
    """多来源官方参数合并：后者覆盖前者（账号级覆盖全局）。"""
    merged: dict[str, Any] = {}
    for source in sources:
        if source:
            merged.update(source)
    return merged


def summarize_limits(limits: dict[str, Any], *, limit: int = 12) -> list[dict[str, Any]]:
    """给页面展示用的精简列表：键 + 值，最多 N 条。"""
    rows = [{"key": key, "value": value} for key, value in sorted(limits.items())]
    return rows[:limit]


__all__ = [
    "FLOOD_TO_THROTTLE",
    "LIMIT_KEY_PREFIXES",
    "LIMIT_KEY_SKIP",
    "OFFICIAL_CLIENTS",
    "OfficialClient",
    "derive_throttle_overrides",
    "extract_dc_options",
    "extract_official_limits",
    "merge_limits",
    "pick_official_client",
    "summarize_limits",
]
