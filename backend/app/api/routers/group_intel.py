"""群情报：入群即采的档案、成员名单与入退群事件流。

采集入口一次说清：
- `POST /group-intel/collect` 对选中的号批量排队采集任务（只读，不发言）；
- 入群/退群事件本身由 Worker 的事件监听被动记录，不需要任何人点按钮；
- 查询侧提供群档案列表、单个群的成员名单、全局事件流与概览，成员支持导 CSV。
"""

from __future__ import annotations

import csv
import io
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, visible_account_ids
from app.api.routers import build_order_by, publish_task_safely
from app.api.routers.accounts_bulk import _empty, _item, _resolve_accounts, _response
from app.config import settings
from app.core.audit import write_audit
from app.core.tasks import enqueue_task
from app.models import (
    GROUP_EVENT_LABELS,
    Dialog,
    DialogChannel,
    DialogKind,
    GroupEvent,
    GroupMember,
    GroupProfile,
    TaskType,
    TgAccount,
    User,
)
from app.schemas import (
    BulkResultResponse,
    CollectLinkRequest,
    GroupCollectRequest,
    GroupEventListResponse,
    GroupEventOut,
    GroupIntelStats,
    GroupMemberListResponse,
    GroupMemberOut,
    GroupProfileListResponse,
    GroupProfileOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/group-intel", tags=["group-intel"])

#: 允许的排序字段（白名单）
PROFILE_SORT = {
    "collected_at": GroupProfile.collected_at,
    "member_count": GroupProfile.member_count,
    "title": GroupProfile.title,
    "created_at": GroupProfile.created_at,
}
MEMBER_SORT = {
    "last_seen_at": GroupMember.last_seen_at,
    "joined_at": GroupMember.joined_at,
    "message_count": GroupMember.message_count,
    "display_name": GroupMember.display_name,
}


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _event_out(event: GroupEvent, titles: dict[int, str]) -> GroupEventOut:
    out = GroupEventOut.model_validate(event)
    out.event_type_label = GROUP_EVENT_LABELS.get(event.event_type, event.event_type)
    out.group_title = titles.get(event.tg_chat_id)
    return out


# ---------------- 采集 ----------------

@router.post("/collect", response_model=BulkResultResponse, summary="批量采集群情报（群档案 + 可选成员）")
async def collect_group_intel(
    payload: GroupCollectRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> BulkResultResponse:
    """对选中的号排队采集任务：每个群一条 `collect_group`，需要名单时再排 `collect_members`。

    这是**只读**操作：只调 `GetFullChannel` / `GetParticipants`，不发言、不回应、不加群。
    """
    accounts, scope, truncated = await _resolve_accounts(session, user, payload)
    if not accounts:
        raise _empty()
    account_ids = [item.id for item in accounts]

    # 目标群：点名 dialog 或该号已同步的全部群
    conditions = [Dialog.channel == DialogChannel.user_account, Dialog.kind == DialogKind.group]
    if payload.dialog_ids:
        conditions.append(Dialog.id.in_(list(dict.fromkeys(payload.dialog_ids))))
    else:
        conditions.append(Dialog.account_id.in_(account_ids))
    dialogs = list(
        (
            await session.scalars(
                select(Dialog).where(*conditions).order_by(Dialog.member_count.desc().nulls_last(), Dialog.id)
            )
        ).all()
    )
    if not dialogs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="没有可采集的群：先让号「同步会话」把群列表拉下来，或在请求里点名 dialog_ids",
        )

    # 按号分组，各自限制 limit_groups，避免一个号被排上百条任务
    per_account: dict[uuid.UUID, list[Dialog]] = {}
    for dialog in dialogs:
        if dialog.account_id is None:
            continue
        bucket = per_account.setdefault(dialog.account_id, [])
        if len(bucket) < payload.limit_groups:
            bucket.append(dialog)

    items = []
    task_ids: List[uuid.UUID] = []
    for account in accounts:
        bucket = per_account.get(account.id, [])
        if not bucket:
            items.append(_item(account, ok=False, message="该号还没有已同步的群"))
            continue
        made = 0
        for dialog in bucket:
            try:
                task = await enqueue_task(
                    session,
                    type=TaskType.collect_group,
                    account_id=account.id,
                    dialog_id=dialog.id,
                    payload={
                        "dialog_id": str(dialog.id),
                        "tg_chat_id": dialog.tg_chat_id,
                        "sample_members": payload.sample_members,
                        "source": "manual_collect",
                    },
                    created_by=user.id,
                    priority=45,
                )
                task_ids.append(task.id)
                made += 1
                if payload.with_members:
                    member_task = await enqueue_task(
                        session,
                        type=TaskType.collect_members,
                        account_id=account.id,
                        dialog_id=dialog.id,
                        payload={
                            "dialog_id": str(dialog.id),
                            "tg_chat_id": dialog.tg_chat_id,
                            "limit": payload.member_limit,
                            "source": "manual_collect",
                        },
                        created_by=user.id,
                        priority=50,
                    )
                    task_ids.append(member_task.id)
            except Exception as exc:  # noqa: BLE001 - 单个群入队失败不影响整批
                logger.warning("群采集入队失败 account_id=%s dialog_id=%s: %s", account.id, dialog.id, exc)
        items.append(
            _item(
                account,
                message=f"已排队 {made} 个群" + ("（含成员名单）" if payload.with_members else "（仅档案）"),
                task_id=None,
            )
        )

    await write_audit(
        session,
        action="group_intel.collect",
        user_id=user.id,
        target_type="account_batch",
        target_id=scope,
        detail={
            "groups": len(dialogs),
            "tasks": len(task_ids),
            "with_members": payload.with_members,
            "sample_members": payload.sample_members,
            "truncated": truncated,
        },
    )
    await session.commit()
    await publish_task_safely(
        {"task_id": None, "type": TaskType.collect_group.value, "ok": True, "detail": f"群情报采集排队 {len(task_ids)} 条任务"}
    )
    return _response(
        "collect",
        accounts,
        items,
        message=f"已排队采集 {len(dialogs)} 个群（{len(task_ids)} 条任务），Worker 会逐个只读拉取",
        truncated=truncated,
        task_ids=task_ids,
    )


@router.post("/collect-link", response_model=BulkResultResponse, summary="按群链接采集群员（自动解析，可选入群）")
async def collect_by_link(
    payload: CollectLinkRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> BulkResultResponse:
    """粘贴群链接 → 系统自动解析群 → 采群档案 + 群员名单。

    链接形式：`https://t.me/xxx`、`t.me/+hash`、`@username`、`-1001234567890` 都能吃。
    **号必须已经在这个群里**才能读到成员名单；不在群里时：
    - 勾选 `join_if_missing` → 先用选中的号加入（按高风险动作计费、过节流），再加群采集；
    - 再勾 `leave_after` → 采完自动退出，群里只留一条入群/退群系统消息。

    多个链接会轮流分给选择范围内的账号（round-robin），避免单个号连续加入多个群。
    """
    accounts, scope, truncated = await _resolve_accounts(session, user, payload)
    if not accounts:
        raise _empty()

    items = []
    task_ids: List[uuid.UUID] = []
    for index, link in enumerate(payload.links):
        # 轮询分配账号：一个号连续进太多群是最容易被风控盯上的形态
        account = accounts[index % len(accounts)]
        try:
            task = await enqueue_task(
                session,
                type=TaskType.collect_link,
                account_id=account.id,
                payload={
                    "link": link,
                    "join_if_missing": payload.join_if_missing,
                    "leave_after": payload.leave_after,
                    "member_limit": payload.member_limit,
                    "source": "link_collect",
                },
                created_by=user.id,
                priority=45,
            )
            task_ids.append(task.id)
            items.append(
                _item(
                    account,
                    message=f"已排队 {link}" + ("（不在群里则先加入）" if payload.join_if_missing else ""),
                    task_id=task.id,
                )
            )
        except Exception as exc:  # noqa: BLE001 - 单个链接入队失败不影响整批
            logger.warning("按链接采集入队失败 account_id=%s link=%s: %s", account.id, link, exc)
            items.append(_item(account, ok=False, message=f"入队失败：{exc}"))

    await write_audit(
        session,
        action="group_intel.collect_link",
        user_id=user.id,
        target_type="account_batch",
        target_id=scope,
        detail={
            "links": len(payload.links),
            "tasks": len(task_ids),
            "join_if_missing": payload.join_if_missing,
            "leave_after": payload.leave_after,
            "member_limit": payload.member_limit,
        },
    )
    await session.commit()
    await publish_task_safely(
        {"task_id": None, "type": TaskType.collect_link.value, "ok": True, "detail": f"按链接采集排队 {len(task_ids)} 条任务"}
    )
    return _response(
        "collect-link",
        accounts,
        items,
        message=(
            f"已排队采集 {len(payload.links)} 个链接（{len(task_ids)} 条任务）"
            + ("；不在群里的号会先加入" if payload.join_if_missing else "；只采已经在群里的号")
            + ("，采完自动退出" if payload.leave_after else "")
        ),
        truncated=truncated,
        task_ids=task_ids,
    )


# ---------------- 群档案 ----------------

@router.get("/profiles", response_model=GroupProfileListResponse, summary="群档案列表")
async def list_profiles(
    q: Optional[str] = Query(default=None, description="按群名/用户名模糊搜索"),
    account_id: Optional[uuid.UUID] = Query(default=None),
    min_members: Optional[int] = Query(default=None, ge=0),
    public_only: bool = Query(default=False, description="只看有公开用户名的群"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    sort: Optional[str] = Query(default=None),
    order: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> GroupProfileListResponse:
    ids = await visible_account_ids(session, user)
    conditions = []
    if ids is not None:
        conditions.append(GroupProfile.account_id.in_(ids))
    if account_id is not None:
        conditions.append(GroupProfile.account_id == account_id)
    if q:
        pattern = f"%{q.strip()}%"
        conditions.append(or_(GroupProfile.title.ilike(pattern), GroupProfile.username.ilike(pattern)))
    if min_members is not None:
        conditions.append(GroupProfile.member_count >= min_members)
    if public_only:
        conditions.append(GroupProfile.username.is_not(None))

    total = await session.scalar(select(func.count()).select_from(GroupProfile).where(*conditions))
    order_by = build_order_by(
        sort=sort,
        order=order,
        mapping=PROFILE_SORT,
        default_field="member_count",
        default_order="desc",
        nulls_last=True,
        tiebreaker=GroupProfile.id,
    )
    rows = list(
        (
            await session.scalars(
                select(GroupProfile)
                .where(*conditions)
                .order_by(*order_by)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    members_total = await session.scalar(
        select(func.count()).select_from(GroupMember).where(GroupMember.tg_chat_id.in_([r.tg_chat_id for r in rows]))
    ) if rows else 0
    today = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    events_today = await session.scalar(
        select(func.count()).select_from(GroupEvent).where(GroupEvent.occurred_at >= today)
    )
    return GroupProfileListResponse(
        items=[GroupProfileOut.model_validate(row) for row in rows],
        total=int(total or 0),
        page=page,
        page_size=page_size,
        summary={
            "groups": int(total or 0),
            "members_collected": int(members_total or 0),
            "events_today": int(events_today or 0),
        },
    )


@router.get("/profiles/{profile_id}", summary="群档案详情（含概览统计）")
async def get_profile(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    profile = await session.get(GroupProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="群档案不存在")
    ids = await visible_account_ids(session, user)
    if ids is not None and (profile.account_id is None or profile.account_id not in set(ids)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="该群不属于分配给你的账号")

    member_rows = await session.execute(
        select(GroupMember.status, func.count())
        .where(GroupMember.tg_chat_id == profile.tg_chat_id)
        .group_by(GroupMember.status)
    )
    counts = {status_value: int(count or 0) for status_value, count in member_rows.all()}
    bots = await session.scalar(
        select(func.count()).select_from(GroupMember).where(
            GroupMember.tg_chat_id == profile.tg_chat_id, GroupMember.is_bot.is_(True)
        )
    )
    event_rows = await session.execute(
        select(GroupEvent.event_type, func.count())
        .where(GroupEvent.tg_chat_id == profile.tg_chat_id)
        .group_by(GroupEvent.event_type)
    )
    return {
        "profile": GroupProfileOut.model_validate(profile),
        "members": {"counts": counts, "bots": int(bots or 0)},
        "events": {key: int(value or 0) for key, value in event_rows.all()},
        "watching": settings.group_intel_watch_enabled,
    }


@router.get("/profiles/{profile_id}/members", response_model=GroupMemberListResponse, summary="群成员名单")
async def list_members(
    profile_id: uuid.UUID,
    q: Optional[str] = Query(default=None, description="按用户名/昵称搜索"),
    only_bots: bool = Query(default=False),
    exclude_bots: bool = Query(default=False),
    member_status: Optional[str] = Query(default=None, alias="status"),
    source: Optional[str] = Query(default=None, description="join_event / participant_sync / message"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    sort: Optional[str] = Query(default=None),
    order: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> GroupMemberListResponse:
    profile = await session.get(GroupProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="群档案不存在")
    ids = await visible_account_ids(session, user)
    if ids is not None and (profile.account_id is None or profile.account_id not in set(ids)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="该群不属于分配给你的账号")

    conditions = [GroupMember.tg_chat_id == profile.tg_chat_id]
    if q:
        pattern = f"%{q.strip()}%"
        conditions.append(or_(GroupMember.username.ilike(pattern), GroupMember.display_name.ilike(pattern)))
    if only_bots:
        conditions.append(GroupMember.is_bot.is_(True))
    if exclude_bots:
        conditions.append(GroupMember.is_bot.is_(False))
    if member_status:
        conditions.append(GroupMember.status == member_status)
    if source:
        conditions.append(GroupMember.source == source)

    total = await session.scalar(select(func.count()).select_from(GroupMember).where(*conditions))
    order_by = build_order_by(
        sort=sort,
        order=order,
        mapping=MEMBER_SORT,
        default_field="last_seen_at",
        default_order="desc",
        nulls_last=True,
        tiebreaker=GroupMember.id,
    )
    rows = list(
        (
            await session.scalars(
                select(GroupMember)
                .where(*conditions)
                .order_by(*order_by)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    count_rows = await session.execute(
        select(GroupMember.status, func.count())
        .where(GroupMember.tg_chat_id == profile.tg_chat_id)
        .group_by(GroupMember.status)
    )
    return GroupMemberListResponse(
        items=[GroupMemberOut.model_validate(row) for row in rows],
        total=int(total or 0),
        page=page,
        page_size=page_size,
        counts={key: int(value or 0) for key, value in count_rows.all()},
    )


# ---------------- 事件流 ----------------

@router.get("/events", response_model=GroupEventListResponse, summary="入退群事件流")
async def list_events(
    tg_chat_id: Optional[int] = Query(default=None),
    event_type: Optional[str] = Query(default=None, description="join / leave / kick / invite"),
    account_id: Optional[uuid.UUID] = Query(default=None),
    hours: int = Query(default=72, ge=1, le=24 * 30, description="看最近多少小时"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> GroupEventListResponse:
    ids = await visible_account_ids(session, user)
    since = _now() - timedelta(hours=hours)
    conditions = [GroupEvent.occurred_at >= since]
    if ids is not None:
        conditions.append(GroupEvent.account_id.in_(ids))
    if tg_chat_id is not None:
        conditions.append(GroupEvent.tg_chat_id == tg_chat_id)
    if event_type:
        conditions.append(GroupEvent.event_type == event_type)
    if account_id is not None:
        conditions.append(GroupEvent.account_id == account_id)

    total = await session.scalar(select(func.count()).select_from(GroupEvent).where(*conditions))
    rows = list(
        (
            await session.scalars(
                select(GroupEvent)
                .where(*conditions)
                .order_by(GroupEvent.occurred_at.desc(), GroupEvent.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    titles: dict[int, str] = {}
    chat_ids = {row.tg_chat_id for row in rows}
    if chat_ids:
        pairs = await session.execute(
            select(GroupProfile.tg_chat_id, GroupProfile.title).where(GroupProfile.tg_chat_id.in_(chat_ids))
        )
        titles = {chat_id: title for chat_id, title in pairs.all()}
    count_rows = await session.execute(
        select(GroupEvent.event_type, func.count()).where(*conditions).group_by(GroupEvent.event_type)
    )
    return GroupEventListResponse(
        items=[_event_out(row, titles) for row in rows],
        total=int(total or 0),
        page=page,
        page_size=page_size,
        counts={key: int(value or 0) for key, value in count_rows.all()},
    )


@router.get("/stats", response_model=GroupIntelStats, summary="群情报概览")
async def group_intel_stats(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> GroupIntelStats:
    ids = await visible_account_ids(session, user)
    base = []
    if ids is not None:
        base.append(GroupProfile.account_id.in_(ids))
    groups = await session.scalar(select(func.count()).select_from(GroupProfile).where(*base))
    member_conditions = list(base) if base else []
    members = await session.scalar(
        select(func.count()).select_from(GroupMember).where(*([GroupMember.account_id.in_(ids)] if ids is not None else []))
    )
    bots = await session.scalar(
        select(func.count())
        .select_from(GroupMember)
        .where(GroupMember.is_bot.is_(True), *([GroupMember.account_id.in_(ids)] if ids is not None else []))
    )
    today = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    event_base = [GroupEvent.occurred_at >= today]
    if ids is not None:
        event_base.append(GroupEvent.account_id.in_(ids))
    events_today = await session.scalar(select(func.count()).select_from(GroupEvent).where(*event_base))
    joins_today = await session.scalar(
        select(func.count()).select_from(GroupEvent).where(*event_base, GroupEvent.event_type.in_(("join", "invite")))
    )
    leaves_today = await session.scalar(
        select(func.count()).select_from(GroupEvent).where(*event_base, GroupEvent.event_type.in_(("leave", "kick")))
    )
    return GroupIntelStats(
        groups=int(groups or 0),
        members=int(members or 0),
        bots=int(bots or 0),
        events_today=int(events_today or 0),
        joins_today=int(joins_today or 0),
        leaves_today=int(leaves_today or 0),
        watching=settings.group_intel_watch_enabled,
    )


@router.get("/members.csv", summary="导出群成员（CSV）")
async def export_members(
    profile_id: Optional[uuid.UUID] = Query(default=None),
    tg_chat_id: Optional[int] = Query(default=None),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    ids = await visible_account_ids(session, user)
    conditions = []
    if ids is not None:
        conditions.append(GroupMember.account_id.in_(ids))
    if profile_id is not None:
        profile = await session.get(GroupProfile, profile_id)
        if profile is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="群档案不存在")
        conditions.append(GroupMember.tg_chat_id == profile.tg_chat_id)
    elif tg_chat_id is not None:
        conditions.append(GroupMember.tg_chat_id == tg_chat_id)
    rows = list(
        (
            await session.scalars(
                select(GroupMember).where(*conditions).order_by(GroupMember.last_seen_at.desc()).limit(20000)
            )
        ).all()
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["群ID", "用户ID", "用户名", "昵称", "是否机器人", "是否会员", "是否管理员", "状态", "来源", "入群时间", "最近出现", "发言数"])
    for row in rows:
        writer.writerow(
            [
                row.tg_chat_id,
                row.tg_user_id,
                row.username or "",
                row.display_name,
                "是" if row.is_bot else "否",
                "是" if row.is_premium else "否",
                "是" if row.is_admin else "否",
                row.status,
                row.source,
                row.joined_at.isoformat() if row.joined_at else "",
                row.last_seen_at.isoformat() if row.last_seen_at else "",
                row.message_count,
            ]
        )
    buffer.seek(0)
    logger.info("导出群成员行数=%s by=%s", len(rows), user.username)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="group-members.csv"'},
    )
