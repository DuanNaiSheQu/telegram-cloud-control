"""关键词监听：消息进来时判断命中了哪条规则。

设计取舍：
- 规则、关键词、命中都放数据库，**匹配在 Worker 内存里做**（每条消息查一次 DB 太慢）；
  Worker 定期刷新规则缓存，改动最多滞后几十秒生效。
- 命中不写新表，落进 `group_events`（`event_type="keyword"`），与入退群流水同一条时间线，
  页面和导出都能直接复用。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KeywordWatch

logger = logging.getLogger(__name__)


def rule_matches(
    rule: Dict[str, Any], *, tg_chat_id: Optional[int], account_id: Optional[str], text: str
) -> Optional[str]:
    """命中判定（纯函数，好测）：返回命中的关键词，没命中返回 None。

    范围为「留空即全部」：规则没限定群就别限制群，没限定号就别限制号——
    运营建规则时通常只想「这个词相关的一切都告诉我」。
    """
    if not rule.get("enabled", True):
        return None
    keywords = [str(k).strip() for k in (rule.get("keywords") or []) if str(k).strip()]
    if not keywords:
        return None
    chats = rule.get("tg_chat_ids") or []
    if chats and tg_chat_id is not None and int(tg_chat_id) not in {int(x) for x in chats}:
        return None
    accounts = {str(x) for x in (rule.get("account_ids") or [])}
    if accounts and account_id is not None and str(account_id) not in accounts:
        return None
    lowered = (text or "").lower()
    if not lowered:
        return None
    for keyword in keywords:
        if keyword.lower() in lowered:
            return keyword
    return None


def scan(
    rules: List[Dict[str, Any]], *, tg_chat_id: Optional[int], account_id: Optional[str], text: str
) -> List[Tuple[Dict[str, Any], str]]:
    """扫一遍所有规则，返回 [(规则, 命中关键词)]。"""
    hits: List[Tuple[Dict[str, Any], str]] = []
    for rule in rules:
        matched = rule_matches(rule, tg_chat_id=tg_chat_id, account_id=account_id, text=text)
        if matched:
            hits.append((rule, matched))
    return hits


async def load_rules(session: AsyncSession) -> List[Dict[str, Any]]:
    """把启用的规则读成纯 dict（Worker 缓存用，避免持有 ORM 对象跨 session）。"""
    rows = list((await session.scalars(select(KeywordWatch).where(KeywordWatch.enabled.is_(True)))).all())
    return [
        {
            "id": str(row.id),
            "name": row.name or "",
            "keywords": list(row.keywords or []),
            "tg_chat_ids": list(row.tg_chat_ids or []),
            "account_ids": [str(x) for x in (row.account_ids or [])],
            "enabled": bool(row.enabled),
            "notify": bool(row.notify),
        }
        for row in rows
    ]


async def record_hit(
    session: AsyncSession,
    *,
    account_id: Any,
    tg_chat_id: int,
    tg_user_id: Optional[int],
    user_display: str,
    keyword: str,
    text: str,
    rule_id: Optional[str] = None,
    rule_name: str = "",
) -> None:
    """命中写进 `group_events`（event_type="keyword"），并给规则计数 +1。

    复用事件流水的好处：页面上的「入退群 + 关键词命中」是同一条时间线，导出也直接带上，
    不用再为命中单独做一套查询与导出。
    """
    from app.models import GroupEvent, KeywordWatch

    session.add(
        GroupEvent(
            account_id=account_id,
            tg_chat_id=int(tg_chat_id),
            tg_user_id=int(tg_user_id) if tg_user_id else None,
            event_type="keyword",
            user_display=(user_display or "")[:128],
            source="keyword_watch",
            raw={
                "keyword": keyword,
                "text": (text or "")[:500],
                "rule_id": rule_id,
                "rule_name": rule_name,
            },
        )
    )
    if rule_id:
        try:
            import uuid as _uuid

            await session.execute(
                sa_update(KeywordWatch)
                .where(KeywordWatch.id == _uuid.UUID(str(rule_id)))
                .values(hit_count=KeywordWatch.hit_count + 1)
            )
        except Exception:  # noqa: BLE001 - 计数失败不影响命中记录本身
            logger.debug("关键词命中计数失败 rule_id=%s", rule_id)
    await session.flush()


async def publish_keyword_notice(
    redis: Any, *, rule_name: str, keyword: str, chat_title: str, sender: str, text: str
) -> None:
    """往 Redis 推一条命中通知（页面实时提示用）；推失败不影响主流程。"""
    if redis is None:
        return
    import json

    try:
        await redis.publish(
            "tgcc:keyword_hit",
            json.dumps(
                {
                    "rule": rule_name,
                    "keyword": keyword,
                    "chat": chat_title,
                    "sender": sender,
                    "text": text,
                },
                ensure_ascii=False,
            ),
        )
    except Exception:  # noqa: BLE001
        logger.debug("关键词通知推送失败", exc_info=True)
