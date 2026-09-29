"""会话 id 的规范化：同一个群/人，只允许一条会话记录。

为什么需要：Telegram 对**频道/超级群**有两套 id 形态——

- 原始 id：`4337589332`（正数）
- 完整 id：`-1004337589332`（`-100` + 原始 id，调用 API 时必须用这个）

同步会话与拉历史走的路径不同，拿到的形态可能不一样，于是同一个群在库里落成**两条会话**，
页面上就出现「一个群两个对话」。这里统一成规范形态后再入库：

| 类型 | 规范形态 |
|---|---|
| 用户（私信） | 正数，如 `8966880282` |
| 频道 / 超级群 | `-100{原始 id}`，如 `-1004337589332` |
| 普通群 | 负数，如 `-123456789`（原本就是负的，原样保留） |

Bot 侧（`777000` 这类官方账号）也是正数，不受影响。
"""

from __future__ import annotations

from typing import Optional

#: 频道/超级群 id 前缀
CHANNEL_PREFIX = "-100"


def normalize_chat_id(tg_chat_id: Optional[int], kind: Optional[str] = None) -> Optional[int]:
    """把会话 id 规范化成唯一形态。

    `kind` 用于判断「正数 id 到底是用户还是频道」：
    - `group` / `channel` 且 id 为正 → 视作频道的原始 id，补 `-100` 前缀；
    - 其它（私信、Bot）→ 保持原样。
    """
    if tg_chat_id is None:
        return None
    value = int(tg_chat_id)
    if value < 0:
        return value  # 已经是完整形态（频道 -100xxx / 普通群 -xxx）
    kind_text = (kind or "").lower()
    if kind_text in ("group", "channel", "megagroup", "supergroup"):
        return int(f"{CHANNEL_PREFIX}{value}")
    return value


def is_same_chat(left: Optional[int], right: Optional[int], kind: Optional[str] = None) -> bool:
    """两个 id 是否指向同一个会话（用于合并历史重复记录）。"""
    return normalize_chat_id(left, kind) == normalize_chat_id(right, kind)


__all__ = ["CHANNEL_PREFIX", "is_same_chat", "normalize_chat_id"]
