"""批量账号操作：检测 / 同步会话 / 分配 / 改分组 / 改代理 / 停用启用 / 清租约。

**边界（规划「不做这些」是硬约束）**：这里只做账号运维层面的批量动作，
不提供任何批量发送、群发、加群、退群、批量改资料的接口——连字段都没有。

权限：
- 账号类动作（检测 / 同步 / 分组 / 代理 / 停用启用 / 清租约）：`assert_accounts_access`
  先把越权账号挡在 403，`scope=all` 对 operator 自动收敛成「分配给他的号」；
- 分配 / 取消分配：员工归属是管理动作，只有 admin 能做。

路由注册顺序很关键：prefix 是 `/accounts/bulk`，必须排在 `accounts.router` 的
`/accounts/{account_id}` 之前，否则 "bulk" 会被当成 UUID 去解析（422）。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    assert_accounts_access,
    get_current_user,
    get_session,
    require_admin,
    scope_clause,
    visible_account_ids,
)
from app.api.routers import build_order_by, enum_value, publish_task_safely
from app.api.routers.accounts import _check_one
from app.core.audit import write_audit
from app.core.tasks import enqueue_task
from app.services.account_availability import split_marketing_usable
from app.services.account_label import account_label as display_label
from app.models import (
    AccountAssignment,
    AccountGroup,
    AccountStatus,
    CurrentTask,
    Lease,
    Proxy,
    TaskType,
    TgAccount,
    User,
)
from app.schemas import (
    BulkAccountResult,
    BulkAppealRequest,
    BulkWarmupRequest,
    BulkProbeRequest,
    BulkThrottleRequest,
    BulkAssignRequest,
    BulkCheckRequest,
    BulkGroupRequest,
    BulkProxyRequest,
    BulkResultResponse,
    BulkScopeRequest,
    BulkStatusRequest,
    BulkSyncRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/accounts/bulk", tags=["accounts"])


# ---------------- 公共工具 ----------------

async def _resolve_accounts(
    session: AsyncSession, user: User, payload: BulkScopeRequest, *, usable_only: bool = False
) -> Tuple[List[TgAccount], str, bool]:
    """把「点名账号 / all / group:<id>」解析成账号行。

    返回 (账号行, 范围标签, 是否被 limit 截断)。越权 403、不存在 404、没匹配到 400。

    `usable_only=True` 时只返回能承接**营销动作**的号（冻结 / 失效 / 停用会被滤掉）——
    这些号写操作必被 Telegram 拒绝，派任务给它们只是白占队列。
    """
    ids = await visible_account_ids(session, user)
    conditions = []
    clause = scope_clause(TgAccount.id, ids)
    if clause is not None:
        conditions.append(clause)

    scope = (payload.scope or "selected").strip()
    if payload.account_ids:
        wanted = list(dict.fromkeys(payload.account_ids))
        await assert_accounts_access(session, user, wanted)
        rows = list((await session.scalars(select(TgAccount).where(TgAccount.id.in_(wanted)))).all())
        found = {item.id for item in rows}
        missing = [item for item in wanted if item not in found]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"账号不存在：{', '.join(str(item) for item in missing)}",
            )
        rows = rows[: payload.limit]
        if usable_only:
            rows, _blocked = split_marketing_usable(rows)
            if not rows:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="选中的账号当前都不能用于营销动作（冻结 / 失效 / 停用）。",
                )
        return rows, f"selected({len(rows)})", False

    if scope == "all":
        pass
    elif scope.startswith("group"):
        raw = scope.split(":", 1)[1].strip() if ":" in scope else ""
        try:
            group_id = uuid.UUID(raw)
        except (ValueError, AttributeError):
            group_id = None
        if group_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="scope 要写成 group:<分组ID>"
            )
        conditions.append(TgAccount.group_id == group_id)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="没有选中任何账号：account_ids 为空时 scope 只能是 all / group:<分组ID>",
        )

    order_by = build_order_by(
        sort=None,
        order=None,
        mapping={"created_at": TgAccount.created_at},
        default_field="created_at",
        default_order="asc",
    )
    rows = list(
        (
            await session.scalars(
                select(TgAccount).where(*conditions).order_by(*order_by).limit(payload.limit + 1)
            )
        ).all()
    )
    truncated = len(rows) > payload.limit
    rows = rows[: payload.limit]
    if usable_only:
        # 冻结 / 失效 / 停用的号写操作必被拒，别派营销任务给它们（省队列、少挨限流）
        rows, _blocked = split_marketing_usable(rows)
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="选中的账号当前都不能用于营销动作（冻结 / 失效 / 停用）。"
                "冻结的号可以先跑「申诉解封」，或在账号管理里换一台可用的号。",
            )
    return rows, scope, truncated


def _item(account: TgAccount, ok: bool = True, message: str = "", **extra) -> BulkAccountResult:
    return BulkAccountResult(
        account_id=account.id,
        # 与列表页同口径：明文手机号 > @用户名 > ID:{tg_user_id}
        account_label=display_label(account) or account.phone_masked or str(account.id)[:8],
        ok=ok,
        message=message,
        **extra,
    )


def _response(
    action: str,
    accounts: List[TgAccount],
    items: List[BulkAccountResult],
    *,
    message: str,
    truncated: bool = False,
    task_ids: Optional[List[uuid.UUID]] = None,
) -> BulkResultResponse:
    succeeded = sum(1 for item in items if item.ok)
    failed = sum(1 for item in items if not item.ok)
    return BulkResultResponse(
        ok=failed == 0,
        action=action,
        message=message,
        requested=len(accounts),
        succeeded=succeeded,
        failed=failed,
        skipped=len(accounts) - len(items),
        truncated=truncated,
        task_ids=task_ids or [],
        items=items,
    )


def _empty(message: str = "没有匹配到账号：请先勾选账号，或用 all / group:<分组ID> 指定范围") -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


# ---------------- 检测 / 同步会话 ----------------

@router.post("/check", response_model=BulkResultResponse, summary="批量检测（写检测任务并续租约）")
async def bulk_check(
    payload: Optional[BulkCheckRequest] = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> BulkResultResponse:
    """对范围内的号逐个走单号检测逻辑：排队 account_check + 立刻回答当前可达性。"""
    payload = payload or BulkCheckRequest()
    accounts, scope, truncated = await _resolve_accounts(session, user, payload)
    if not accounts:
        raise _empty()

    now = None
    items: List[BulkAccountResult] = []
    task_ids: List[uuid.UUID] = []
    for account in accounts:
        try:
            result = await _check_one(session, user, account, now)
            task_ids.append(result.task_id) if result.task_id else None
            items.append(
                _item(
                    account,
                    reachable=result.reachable,
                    status=enum_value(result.status),
                    status_label=result.status_label,
                    message=result.message,
                    task_id=result.task_id,
                )
            )
        except Exception as exc:  # noqa: BLE001 - 单个号失败不影响整批
            logger.warning("批量检测单号失败 account_id=%s: %s", account.id, exc)
            items.append(_item(account, ok=False, message=f"检测入队失败：{exc}"))

    await write_audit(
        session,
        action="account.bulk_check",
        user_id=user.id,
        target_type="account_batch",
        target_id=scope,
        detail={"count": len(items), "scope": scope, "truncated": truncated},
    )
    await session.commit()
    return _response(
        "check",
        accounts,
        items,
        message=f"已排队检测 {len(items)} 个账号，结果会写回各自的账号行",
        truncated=truncated,
        task_ids=task_ids,
    )


@router.post("/sync-dialogs", response_model=BulkResultResponse, summary="批量同步会话列表")
async def bulk_sync_dialogs(
    payload: Optional[BulkSyncRequest] = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> BulkResultResponse:
    """给每个号写一条 sync_dialogs 任务，由持有租约的 Worker 拉群和私信。"""
    payload = payload or BulkSyncRequest()
    accounts, scope, truncated = await _resolve_accounts(session, user, payload)
    if not accounts:
        raise _empty()

    items: List[BulkAccountResult] = []
    task_ids: List[uuid.UUID] = []
    for account in accounts:
        try:
            task = await enqueue_task(
                session,
                type=TaskType.sync_dialogs,
                account_id=account.id,
                payload={},
                created_by=user.id,
                priority=60,
            )
            task_ids.append(task.id)
            items.append(_item(account, message="已排队同步会话", task_id=task.id))
        except Exception as exc:  # noqa: BLE001
            logger.warning("批量同步会话入队失败 account_id=%s: %s", account.id, exc)
            items.append(_item(account, ok=False, message=f"入队失败：{exc}"))

    await write_audit(
        session,
        action="account.bulk_sync_dialogs",
        user_id=user.id,
        target_type="account_batch",
        target_id=scope,
        detail={"count": len(items), "scope": scope, "truncated": truncated},
    )
    await session.commit()
    await publish_task_safely(
        {
            "task_id": None,
            "type": TaskType.sync_dialogs.value,
            "ok": True,
            "detail": f"批量同步 {len(task_ids)} 个账号的会话",
        }
    )
    return _response(
        "sync-dialogs",
        accounts,
        items,
        message=f"已排队同步 {len(items)} 个账号的会话，等持有租约的 Worker 执行",
        truncated=truncated,
        task_ids=task_ids,
    )


# ---------------- 分配 / 取消分配（admin） ----------------

@router.post("/assign", response_model=BulkResultResponse, summary="批量分配 / 取消分配（仅 admin）")
async def bulk_assign(
    payload: BulkAssignRequest,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> BulkResultResponse:
    """把范围内的号分配给某个员工，或取消分配（mode=unassign）。重复分配自动跳过。"""
    mode = (payload.mode or "assign").strip().lower()
    if mode not in ("assign", "unassign"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="mode 只能是 assign 或 unassign")

    target = await session.scalar(select(User).where(User.id == payload.user_id))
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="员工不存在")

    accounts, scope, truncated = await _resolve_accounts(session, admin, payload)
    if not accounts:
        raise _empty()
    account_ids = [item.id for item in accounts]

    existing = set(
        (
            await session.scalars(
                select(AccountAssignment.account_id).where(
                    AccountAssignment.user_id == target.id,
                    AccountAssignment.account_id.in_(account_ids),
                )
            )
        ).all()
    )

    items: List[BulkAccountResult] = []
    if mode == "assign":
        added = [item for item in account_ids if item not in existing]
        for account_id in added:
            session.add(AccountAssignment(user_id=target.id, account_id=account_id))
        await session.flush()
        for account in accounts:
            if account.id in existing:
                items.append(_item(account, message="本来就已分配，跳过"))
            else:
                items.append(_item(account, message=f"已分配给 {target.username}"))
        message = f"已把 {len(added)} 个账号分配给 {target.username}（{len(existing)} 个原本就已分配）"
        action = "account.bulk_assign"
    else:
        removed = [item for item in account_ids if item in existing]
        if removed:
            await session.execute(
                delete(AccountAssignment).where(
                    AccountAssignment.user_id == target.id,
                    AccountAssignment.account_id.in_(removed),
                )
            )
        for account in accounts:
            if account.id in removed:
                items.append(_item(account, message=f"已取消 {target.username} 的分配"))
            else:
                items.append(_item(account, message="本来就没分配给他，跳过"))
        message = f"已取消 {len(removed)} 个账号对 {target.username} 的分配"
        action = "account.bulk_unassign"

    await write_audit(
        session,
        action=action,
        user_id=admin.id,
        target_type="user",
        target_id=str(target.id),
        detail={"mode": mode, "scope": scope, "count": len(items), "truncated": truncated},
    )
    await session.commit()
    if mode == "unassign":
        # 保留分配数统计口径：取消后该员工立刻看不到这些号（可见范围每次实时查库）
        logger.info("批量取消分配 user=%s count=%s", target.username, len(items))
    return _response(mode, accounts, items, message=message, truncated=truncated)


# ---------------- 改分组 / 改代理 ----------------

@router.post("/group", response_model=BulkResultResponse, summary="批量改分组（null = 移出分组）")
async def bulk_group(
    payload: Optional[BulkGroupRequest] = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> BulkResultResponse:
    """只改 tg_accounts.group_id；`group_id=null` 表示移出分组（号本身不动）。"""
    payload = payload or BulkGroupRequest()
    group = None
    if payload.group_id is not None:
        group = await session.scalar(select(AccountGroup).where(AccountGroup.id == payload.group_id))
        if group is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="分组不存在")

    accounts, scope, truncated = await _resolve_accounts(session, user, payload)
    if not accounts:
        raise _empty()
    account_ids = [item.id for item in accounts]
    await session.execute(
        update(TgAccount).where(TgAccount.id.in_(account_ids)).values(group_id=payload.group_id)
    )
    label = f"分组「{group.name}」" if group is not None else "未分组"
    items = [_item(account, message=f"已归到{label}") for account in accounts]
    await write_audit(
        session,
        action="account.bulk_group",
        user_id=user.id,
        target_type="account_batch",
        target_id=scope,
        detail={"group_id": str(payload.group_id) if payload.group_id else None, "count": len(items)},
    )
    await session.commit()
    return _response(
        "group",
        accounts,
        items,
        message=f"已把 {len(items)} 个账号归到{label}",
        truncated=truncated,
    )


@router.post("/proxy", response_model=BulkResultResponse, summary="批量改代理（null = 改为直连）")
async def bulk_proxy(
    payload: Optional[BulkProxyRequest] = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> BulkResultResponse:
    """只改 tg_accounts.proxy_id；`proxy_id=null` 表示改为直连。Worker 下次续租时读取。"""
    payload = payload or BulkProxyRequest()
    proxy = None
    if payload.proxy_id is not None:
        proxy = await session.scalar(select(Proxy).where(Proxy.id == payload.proxy_id))
        if proxy is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="代理不存在")

    accounts, scope, truncated = await _resolve_accounts(session, user, payload)
    if not accounts:
        raise _empty()
    account_ids = [item.id for item in accounts]
    await session.execute(
        update(TgAccount).where(TgAccount.id.in_(account_ids)).values(proxy_id=payload.proxy_id)
    )
    label = f"代理「{proxy.name}」" if proxy is not None else "直连"
    items = [_item(account, message=f"已改为{label}") for account in accounts]
    await write_audit(
        session,
        action="account.bulk_proxy",
        user_id=user.id,
        target_type="account_batch",
        target_id=scope,
        detail={"proxy_id": str(payload.proxy_id) if payload.proxy_id else None, "count": len(items)},
    )
    await session.commit()
    return _response(
        "proxy", accounts, items, message=f"已把 {len(items)} 个账号改为{label}", truncated=truncated
    )


# ---------------- 停用 / 启用 / 清租约 ----------------

async def _disable_accounts(session: AsyncSession, accounts: List[TgAccount]) -> int:
    """停用一批号：状态置 disabled + 当前任务归零 + 清租约（Worker 会主动断开这些号）。"""
    account_ids = [item.id for item in accounts]
    await session.execute(
        update(TgAccount)
        .where(TgAccount.id.in_(account_ids))
        .values(status=AccountStatus.disabled, current_task=CurrentTask.idle)
    )
    result = await session.execute(delete(Lease).where(Lease.account_id.in_(account_ids)))
    return int(result.rowcount or 0)


async def _enable_accounts(session: AsyncSession, accounts: List[TgAccount]) -> None:
    """启用一批号：有会话回 healthy，没有会话回 pending。"""
    healthy_ids = [item.id for item in accounts if item.session_enc]
    pending_ids = [item.id for item in accounts if not item.session_enc]
    if healthy_ids:
        await session.execute(
            update(TgAccount)
            .where(TgAccount.id.in_(healthy_ids))
            .values(status=AccountStatus.healthy, last_error="")
        )
    if pending_ids:
        await session.execute(
            update(TgAccount)
            .where(TgAccount.id.in_(pending_ids))
            .values(status=AccountStatus.pending, last_error="")
        )


def _status_response(
    action: str,
    accounts: List[TgAccount],
    *,
    enabled: bool,
    truncated: bool,
    released: int = 0,
) -> BulkResultResponse:
    if enabled:
        items = [
            _item(
                account,
                message="已启用，Worker 会在下一轮续租时接管"
                if account.session_enc
                else "该号还没有会话，已回到待登录",
            )
            for account in accounts
        ]
        message = f"已启用 {len(items)} 个账号"
    else:
        items = [_item(account, message="已停用并清除租约") for account in accounts]
        message = f"已停用 {len(items)} 个账号"
        if released:
            message += f"，清掉 {released} 个租约"
    return _response(action, accounts, items, message=message, truncated=truncated)


async def _bulk_status(
    payload: BulkStatusRequest,
    session: AsyncSession,
    user: User,
    *,
    enabled: bool,
    action: str,
    audit_action: str,
) -> BulkResultResponse:
    accounts, scope, truncated = await _resolve_accounts(session, user, payload)
    if not accounts:
        raise _empty()
    released = 0
    if enabled:
        await _enable_accounts(session, accounts)
    else:
        released = await _disable_accounts(session, accounts)
    await write_audit(
        session,
        action=audit_action,
        user_id=user.id,
        target_type="account_batch",
        target_id=scope,
        detail={"count": len(accounts), "enabled": enabled, "released_leases": released},
    )
    await session.commit()
    return _status_response(action, accounts, enabled=enabled, truncated=truncated, released=released)


@router.post("/status", response_model=BulkResultResponse, summary="批量停用 / 启用")
async def bulk_status(
    payload: Optional[BulkStatusRequest] = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> BulkResultResponse:
    """`enabled=false` 停用并清租约；`enabled=true` 启用（有会话回 healthy，否则回 pending）。"""
    payload = payload or BulkStatusRequest()
    return await _bulk_status(
        payload,
        session,
        user,
        enabled=payload.enabled,
        action="status",
        audit_action="account.bulk_enable" if payload.enabled else "account.bulk_disable",
    )


@router.post("/disable", response_model=BulkResultResponse, summary="批量停用（status 的别名）")
async def bulk_disable(
    payload: Optional[BulkStatusRequest] = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> BulkResultResponse:
    """等价于 `POST /accounts/bulk/status {"enabled": false}`；前端按钮直接调这个更省事。"""
    payload = payload or BulkStatusRequest()
    return await _bulk_status(
        payload, session, user, enabled=False, action="disable", audit_action="account.bulk_disable"
    )


@router.post("/enable", response_model=BulkResultResponse, summary="批量启用（status 的别名）")
async def bulk_enable(
    payload: Optional[BulkStatusRequest] = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> BulkResultResponse:
    """等价于 `POST /accounts/bulk/status {"enabled": true}`。"""
    payload = payload or BulkStatusRequest()
    return await _bulk_status(
        payload, session, user, enabled=True, action="enable", audit_action="account.bulk_enable"
    )


@router.post("/release-lease", response_model=BulkResultResponse, summary="批量清除租约")
async def bulk_release_lease(
    payload: Optional[BulkScopeRequest] = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> BulkResultResponse:
    """只清租约，不改状态：号异常卡在某个 Worker 上时用，其它号不受影响。"""
    payload = payload or BulkScopeRequest()
    accounts, scope, truncated = await _resolve_accounts(session, user, payload)
    if not accounts:
        raise _empty()
    account_ids = [item.id for item in accounts]
    result = await session.execute(delete(Lease).where(Lease.account_id.in_(account_ids)))
    released = int(result.rowcount or 0)
    await session.execute(
        update(TgAccount).where(TgAccount.id.in_(account_ids)).values(current_task=CurrentTask.idle)
    )
    items = [_item(account, message="已清除租约") for account in accounts]
    await write_audit(
        session,
        action="account.bulk_release_lease",
        user_id=user.id,
        target_type="account_batch",
        target_id=scope,
        detail={"count": len(items), "released": released},
    )
    await session.commit()
    message = f"已清除 {len(items)} 个账号的租约" + (f"（实际释放 {released} 个）" if released else "（原本就没有租约）")
    return _response("release-lease", accounts, items, message=message, truncated=truncated)

# ---------------- 账号矩阵：批量节流 / 深度验活 ----------------

@router.post("/throttle", response_model=BulkResultResponse, summary="批量设置节流（每日上限 / 动作间隔 / 解熔断）")
async def bulk_throttle(
    payload: BulkThrottleRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> BulkResultResponse:
    """给一批号设定发送额度与最小间隔，是防封的主要旋钮。

    - `daily_message_limit`：每日发送上限；传 `0` 表示回到「按号龄自动阶梯」；
    - `min_action_seconds`：两次动作之间的最小间隔；传 `0` 同样回到自动；
    - `start_warmup_now`：把养号起点重置为现在（刚批量导入的新号用，阶梯从最严档开始）；
    - `reset_flood`：清掉熔断冷却与限流计数（确认号已经恢复再点）。
    """
    accounts, scope, truncated = await _resolve_accounts(session, user, payload)
    if not accounts:
        raise _empty()

    now = datetime.now(tz=timezone.utc)
    changed = 0
    items = []
    for account in accounts:
        notes: list[str] = []
        if payload.daily_message_limit is not None:
            account.daily_message_limit = int(payload.daily_message_limit)
            notes.append("额度按自动阶梯" if payload.daily_message_limit == 0 else f"每日上限 {payload.daily_message_limit}")
        if payload.min_action_seconds is not None:
            account.min_action_seconds = int(payload.min_action_seconds)
            notes.append("间隔按自动阶梯" if payload.min_action_seconds == 0 else f"最小间隔 {payload.min_action_seconds} 秒")
        if payload.start_warmup_now:
            account.warmup_started_at = now
            notes.append("养号起点重置为今天")
        if payload.reset_flood:
            account.flood_until = None
            account.flood_strikes = 0
            flags = dict(account.risk_flags or {})
            flags.pop("downgrade", None)
            account.risk_flags = flags
            notes.append("已解除熔断")
        changed += 1
        items.append(_item(account, message="；".join(notes) or "未变更"))

    await session.flush()
    await write_audit(
        session,
        action="account.bulk_throttle",
        user_id=user.id,
        target_type="account_batch",
        target_id=scope,
        detail={
            "count": len(items),
            "daily_message_limit": payload.daily_message_limit,
            "min_action_seconds": payload.min_action_seconds,
            "reset_flood": payload.reset_flood,
            "start_warmup_now": payload.start_warmup_now,
            "truncated": truncated,
        },
    )
    await session.commit()
    return _response(
        "throttle",
        accounts,
        items,
        message=f"已更新 {changed} 个账号的节流设置（额度/间隔传 0 即回到按号龄自动阶梯）",
        truncated=truncated,
    )


@router.post("/probe", response_model=BulkResultResponse, summary="批量深度验活（连得上 + 会话有效 + 读写权限）")
async def bulk_probe(
    payload: Optional[BulkProbeRequest] = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> BulkResultResponse:
    """排队深度验活：由持有租约的 Worker 逐个连上去读账号状态，复算健康分。

    与普通检测的区别：普通检测只确认「连得上」；深度验活还会读会话列表、统计授权会话数、
    可选做一次写权限探测（往自己的收藏夹发一条），把结果写进 `health_score` / `health_detail`。
    """
    payload = payload or BulkProbeRequest()
    accounts, scope, truncated = await _resolve_accounts(session, user, payload)
    if not accounts:
        raise _empty()

    items: List[BulkAccountResult] = []
    task_ids: List[uuid.UUID] = []
    for account in accounts:
        try:
            task = await enqueue_task(
                session,
                type=TaskType.account_check,
                account_id=account.id,
                payload={"deep": True, "write_probe": bool(payload.write_probe), "source": "bulk_probe"},
                created_by=user.id,
                priority=40,
            )
            task_ids.append(task.id)
            items.append(_item(account, message="已排队深度验活", task_id=task.id))
        except Exception as exc:  # noqa: BLE001
            logger.warning("深度验活入队失败 account_id=%s: %s", account.id, exc)
            items.append(_item(account, ok=False, message=f"入队失败：{exc}"))

    await write_audit(
        session,
        action="account.bulk_probe",
        user_id=user.id,
        target_type="account_batch",
        target_id=scope,
        detail={"count": len(items), "write_probe": payload.write_probe, "truncated": truncated},
    )
    await session.commit()
    await publish_task_safely(
        {"task_id": None, "type": TaskType.account_check.value, "ok": True, "detail": f"批量深度验活 {len(task_ids)} 个号"}
    )
    return _response(
        "probe",
        accounts,
        items,
        message=f"已排队深度验活 {len(items)} 个账号，结果会写回各自的健康分",
        truncated=truncated,
        task_ids=task_ids,
    )

# ---------------- 官方机制：养号活动 ----------------

@router.post("/warmup", response_model=BulkResultResponse, summary="官方机制养号（上线/翻会话/下线，不发消息）")
async def bulk_warmup(
    payload: BulkWarmupRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> BulkResultResponse:
    """给选中的号排队「官方节奏养号活动」：上线 → 翻会话列表 → 下线，全程不发消息、不加群。

    为什么这么做：风控看行为分布——从不读、永远离线、只在特定时刻精准发消息的会话本身就是异常特征；
    官方客户端的读/在线节奏是最不异常的模板。默认**不**开已读与打字状态（那两项对方可见）。

    `sync_limits=true` 时会额外排一条官方参数同步任务：把服务端下发的 flood/上限参数拉下来，
    后续节流「只收紧不放松」地参考它们。
    """
    accounts, scope, truncated = await _resolve_accounts(session, user, payload)
    if not accounts:
        raise _empty()

    items: List[BulkAccountResult] = []
    task_ids: List[uuid.UUID] = []
    for account in accounts:
        try:
            task = await enqueue_task(
                session,
                type=TaskType.warmup_activity,
                account_id=account.id,
                payload={
                    "rounds": payload.rounds,
                    "online_min_seconds": payload.online_min_seconds,
                    "online_max_seconds": payload.online_max_seconds,
                    "read_inbox": payload.read_inbox,
                    "typing": payload.typing,
                    "source": "bulk_warmup",
                },
                created_by=user.id,
                priority=60,
            )
            task_ids.append(task.id)
            made: list[str] = [f"养号 {payload.rounds} 轮"]
            if payload.sync_limits:
                limits_task = await enqueue_task(
                    session,
                    type=TaskType.sync_official,
                    account_id=account.id,
                    payload={"source": "bulk_warmup"},
                    created_by=user.id,
                    priority=55,
                )
                task_ids.append(limits_task.id)
                made.append("同步官方参数")
            items.append(_item(account, message=" + ".join(made)))
        except Exception as exc:  # noqa: BLE001 - 单个号入队失败不影响整批
            logger.warning("养号入队失败 account_id=%s: %s", account.id, exc)
            items.append(_item(account, ok=False, message=f"入队失败：{exc}"))

    await write_audit(
        session,
        action="account.bulk_warmup",
        user_id=user.id,
        target_type="account_batch",
        target_id=scope,
        detail={
            "count": len(items),
            "rounds": payload.rounds,
            "read_inbox": payload.read_inbox,
            "typing": payload.typing,
            "sync_limits": payload.sync_limits,
            "truncated": truncated,
        },
    )
    await session.commit()
    await publish_task_safely(
        {"task_id": None, "type": TaskType.warmup_activity.value, "ok": True, "detail": f"官方养号排队 {len(task_ids)} 条任务"}
    )
    return _response(
        "warmup",
        accounts,
        items,
        message=(
            f"已排队 {len(items)} 个号的养号活动"
            + ("（含官方参数同步）" if payload.sync_limits else "")
            + "；活动期间只上线与翻会话，不发任何消息"
        ),
        truncated=truncated,
        task_ids=task_ids,
    )

# ---------------- 申诉解封（模拟真人走官方流程） ----------------

@router.post("/appeal", response_model=BulkResultResponse, summary="申诉解封（模拟真人给 @SpamBot 发 /start 并点击申诉）")
async def bulk_appeal(
    payload: BulkAppealRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> BulkResultResponse:
    """对被限制/冻结的号排队「申诉解封」：模拟真人操作官方 @SpamBot。

    流程就是真人会做的：打开 SpamBot → 发 `/start` → 看它判定 → 有「这是误判」按钮就点一下 → 记录结果。
    几个安全边界：

    - **同一账号 24 小时只申诉一次**（反复打扰官方反而更难解）；
    - 只做正常会话动作，不发送任何内容给对方之外的任何人；
    - 结论写回账号：无限制 → 恢复正常；已提交 → 记下按钮与等待状态。
    """
    accounts, scope, truncated = await _resolve_accounts(session, user, payload)
    if not accounts:
        raise _empty()

    items: List[BulkAccountResult] = []
    task_ids: List[uuid.UUID] = []
    for account in accounts:
        # 24 小时内申诉过就跳过，省得白排一条注定失败的任务
        flags = dict(account.risk_flags or {})
        last_at = flags.get("last_appeal_at")
        if last_at:
            try:
                hours = (datetime.now(tz=timezone.utc) - datetime.fromisoformat(str(last_at))).total_seconds() / 3600
                if hours < 24:
                    items.append(_item(account, ok=False, message=f"{hours:.1f} 小时前刚申诉过，24 小时内不重复"))
                    continue
            except ValueError:
                pass
        try:
            task = await enqueue_task(
                session,
                type=TaskType.appeal_spam,
                account_id=account.id,
                payload={"source": "bulk_appeal"},
                created_by=user.id,
                priority=55,
            )
            task_ids.append(task.id)
            note = "申诉解封"
            if payload.with_warmup:
                warm = await enqueue_task(
                    session,
                    type=TaskType.warmup_activity,
                    account_id=account.id,
                    payload={"rounds": 1, "source": "bulk_appeal"},
                    created_by=user.id,
                    priority=60,
                )
                task_ids.append(warm.id)
                note += " + 养号一轮"
            items.append(_item(account, message=note))
        except Exception as exc:  # noqa: BLE001
            logger.warning("申诉入队失败 account_id=%s: %s", account.id, exc)
            items.append(_item(account, ok=False, message=f"入队失败：{exc}"))

    await write_audit(
        session,
        action="account.bulk_appeal",
        user_id=user.id,
        target_type="account_batch",
        target_id=scope,
        detail={"count": len(items), "with_warmup": payload.with_warmup, "truncated": truncated},
    )
    await session.commit()
    await publish_task_safely(
        {"task_id": None, "type": TaskType.appeal_spam.value, "ok": True, "detail": f"申诉解封排队 {len(task_ids)} 条任务"}
    )
    return _response(
        "appeal",
        accounts,
        items,
        message=(
            f"已排队 {len(items)} 个号的申诉流程（模拟真人给 @SpamBot 发 /start 并点击申诉）"
            + ("；每个号顺带养号一轮" if payload.with_warmup else "")
        ),
        truncated=truncated,
        task_ids=task_ids,
    )
