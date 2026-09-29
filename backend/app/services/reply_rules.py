"""账号自动回复：拿收到的消息去匹配规则，命中就回一句。

与关键词监听的分工：监听是「记下来给人看」（不打扰对方），回复规则是「真的回一句」。
因此回复这条链路多两道闸：**冷却**（同一会话隔一会儿才回，避免刷屏）与**节流/配额**
（发出去的每条都算该号的发送额度，不能绕过防封机制）。
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ReplyRule

logger = logging.getLogger(__name__)

#: 会话冷却：key = (规则id, 会话id) → 上次回复的单调时间
_COOLDOWN: Dict[tuple, float] = {}


def match_rule(
    rule: Dict[str, Any], *, text: str, scope: str, account_id: Optional[str]
) -> Optional[str]:
    """命中判定：返回命中的关键词/模式，没命中返回 None。

    `scope` 是这条消息的来路（private / group），规则范围 `both` 时都回。
    """
    if not rule.get("enabled", True):
        return None
    rule_scope = str(rule.get("scope") or "private")
    if rule_scope != "both" and rule_scope != scope:
        return None
    accounts = {str(x) for x in (rule.get("account_ids") or [])}
    if accounts and account_id is not None and str(account_id) not in accounts:
        return None

    keywords = [str(k).strip() for k in (rule.get("keywords") or []) if str(k).strip()]
    if not keywords:
        return None
    mode = str(rule.get("match_mode") or "contains")
    body = text or ""
    for keyword in keywords:
        if mode == "exact":
            if body.strip() == keyword:
                return keyword
        elif mode == "regex":
            try:
                if re.search(keyword, body):
                    return keyword
            except re.error:
                logger.warning("回复规则正则非法，已跳过：%s", keyword)
                continue
        else:  # contains
            if keyword.lower() in body.lower():
                return keyword
    return None


def pick_rule(
    rules: List[Dict[str, Any]], *, text: str, scope: str, account_id: Optional[str]
) -> Optional[Dict[str, Any]]:
    """按优先级挑一条命中的规则（数字小的先匹配）。"""
    for rule in sorted(rules, key=lambda item: int(item.get("priority") or 100)):
        if match_rule(rule, text=text, scope=scope, account_id=account_id):
            return rule
    return None


def cooling_down(rule_id: str, dialog_id: str, cooldown: int) -> bool:
    """同一会话是否还在冷却期内（避免对方连发几条就回几条）。"""
    if cooldown <= 0:
        return False
    key = (rule_id, dialog_id)
    last = _COOLDOWN.get(key)
    now = time.monotonic()
    if last is not None and now - last < cooldown:
        return True
    _COOLDOWN[key] = now
    # 简单清理，防止长时间运行后字典无限增长
    if len(_COOLDOWN) > 5000:
        cutoff = now - 3600
        for stale in [k for k, v in _COOLDOWN.items() if v < cutoff]:
            _COOLDOWN.pop(stale, None)
    return False


async def load_reply_rules(session: AsyncSession) -> List[Dict[str, Any]]:
    """读启用规则为纯 dict（Worker 缓存用）。"""
    rows = list((await session.scalars(select(ReplyRule).where(ReplyRule.enabled.is_(True)))).all())
    return [
        {
            "id": str(row.id),
            "name": row.name or "",
            "keywords": list(row.keywords or []),
            "reply_text": row.reply_text or "",
            "match_mode": row.match_mode or "contains",
            "scope": row.scope or "private",
            "account_ids": [str(x) for x in (row.account_ids or [])],
            "enabled": bool(row.enabled),
            "priority": int(row.priority or 100),
            "cooldown_seconds": int(row.cooldown_seconds or 0),
        }
        for row in rows
    ]


async def bump_hit(session: AsyncSession, rule_id: str) -> None:
    """命中计数 +1（失败不影响回复本身）。"""
    if not rule_id:
        return
    import uuid as _uuid

    from sqlalchemy import update

    try:
        await session.execute(
            update(ReplyRule)
            .where(ReplyRule.id == _uuid.UUID(str(rule_id)))
            .values(hit_count=ReplyRule.hit_count + 1)
        )
    except Exception:  # noqa: BLE001
        logger.debug("回复规则计数失败 rule_id=%s", rule_id)
