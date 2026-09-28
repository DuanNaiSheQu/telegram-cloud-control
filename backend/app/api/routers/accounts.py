"""账号管理：列表 / 建档 / 登录三步 / 检测 / 停用启用 / 清租约 / 同步会话 / 改资料。

约定：所有写操作都只写 `tasks` 表（登录、同步、发送、检测、改资料都由持有租约的 Worker 执行），
API 自己不连 Telethon。测试也不改任何模型 / 迁移。
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app import security
from app.api.deps import (
    assert_account_access,
    get_current_user,
    get_session,
    scope_clause,
    visible_account_ids,
)
from app.api.routers import (
    account_out,
    build_order_by,
    dialog_out,
    enum_value,
    group_out,
    message_out,
    proxy_out,
    publish_task_safely,
    task_out,
    unloaded_attr,
    user_label,
    utcnow,
)
from app.core import events, leases
from app.core.audit import ACTION_LABELS, write_audit
from app.core.tasks import enqueue_task
from app.models import (
    ACCOUNT_STATUS_LABELS,
    AccountGroup,
    AccountStatus,
    AuditLog,
    CurrentTask,
    Dialog,
    DialogKind,
    Lease,
    Message,
    Proxy,
    Task,
    TaskStatus,
    TaskType,
    TgAccount,
    User,
)
from app.redis_client import get_redis
from app.schemas import (
    AccountCreate,
    AccountListResponse,
    AccountOut,
    AccountOverviewOut,
    AccountSummary,
    AccountUpdate,
    AuditOut,
    CheckRequest,
    CheckResultOut,
    DialogStats,
    LeaseDetail,
    LoginCodeRequest,
    LoginPasswordRequest,
    LoginStartRequest,
    LoginStepResponse,
    TaskStats,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/accounts", tags=["accounts"])

#: 一次「全部检测」最多排队多少个号，防止误点把任务表灌爆
MAX_CHECK_BATCH = 1000

#: 账号列表允许的排序字段（白名单，避免拿任意列排序）
ACCOUNT_SORT_FIELDS = {
    "created_at": TgAccount.created_at,
    "updated_at": TgAccount.updated_at,
    "phone_masked": TgAccount.phone_masked,
    "username": TgAccount.username,
    "display_name": TgAccount.display_name,
    "status": TgAccount.status,
    "current_task": TgAccount.current_task,
    "age_days": TgAccount.age_days,
    "group_count": TgAccount.group_count,
    "last_heartbeat": TgAccount.last_heartbeat,
    "last_checked_at": TgAccount.last_checked_at,
}

#: 详情聚合抽屉每块的条数
OVERVIEW_DIALOG_LIMIT = 20
OVERVIEW_MESSAGE_LIMIT = 50
OVERVIEW_TASK_LIMIT = 20
OVERVIEW_AUDIT_LIMIT = 20


class ProfileUpdateRequest(BaseModel):
    """改本号资料：只传要改的字段，None 表示不动。"""

    first_name: Optional[str] = Field(default=None, max_length=64)
    last_name: Optional[str] = Field(default=None, max_length=64)
    bio: Optional[str] = Field(default=None, max_length=255)
    username: Optional[str] = Field(default=None, max_length=32)
    photo_url: Optional[str] = Field(default=None, max_length=512)


# ---------------- 模块内工具 ----------------

def _digits(value: Optional[str]) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


async def _load_account(session: AsyncSession, account_id: uuid.UUID) -> TgAccount:
    account = await session.scalar(select(TgAccount).where(TgAccount.id == account_id))
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")
    return account


async def _reload_account(session: AsyncSession, account_id: uuid.UUID) -> TgAccount:
    """改完后重新查一次，返回最新值。

    注意：group / proxy 关系在首次查询后就缓存进 identity map，改完再查不会刷新，
    PATCH 响应会「滞后一拍」返回改前的关系数据（DB 其实已生效）。这里用
    populate_existing + joinedload 强制用库里最新值覆盖。
    """
    await _load_account(session, account_id)
    account = await session.scalar(
        select(TgAccount)
        .where(TgAccount.id == account_id)
        .options(joinedload(TgAccount.group), joinedload(TgAccount.proxy))
        .execution_options(populate_existing=True)
    )
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")
    return account


async def _find_by_phone(session: AsyncSession, phone: str) -> Optional[TgAccount]:
    """按手机号找已建档的号。

    脱敏值会碰撞（同一个 mask 可能对应不同号），所以先用 phone_masked 粗筛，
    再解密 phone_enc 精确比对数字部分。这样重复建档不会产生第二个号。
    """
    masked = security.mask_phone(phone)
    wanted = _digits(phone)
    rows = await session.scalars(select(TgAccount).where(TgAccount.phone_masked == masked))
    for row in rows.all():
        if not row.phone_enc:
            continue
        try:
            stored = security.decrypt_secret(row.phone_enc)
        except ValueError:  # 密钥轮换过，跳过这条
            continue
        if _digits(stored) == wanted:
            return row
    return None


async def _validate_refs(
    session: AsyncSession,
    group_id: Optional[uuid.UUID],
    proxy_id: Optional[uuid.UUID],
) -> None:
    if group_id is not None:
        exists = await session.scalar(select(AccountGroup.id).where(AccountGroup.id == group_id))
        if exists is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="分组不存在")
    if proxy_id is not None:
        exists = await session.scalar(select(Proxy.id).where(Proxy.id == proxy_id))
        if exists is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="代理不存在")


async def _summary(session: AsyncSession, ids: Optional[List[uuid.UUID]]) -> AccountSummary:
    """页面四块汇总 + 在线 / 占用。范围与列表一致（operator 只统计分配到的号）。"""
    scope = [] if ids is None else [TgAccount.id.in_(ids)]
    now = utcnow()
    week_ago = now - timedelta(days=7)

    total = await session.scalar(select(func.count()).select_from(TgAccount).where(*scope))
    healthy = await session.scalar(
        select(func.count())
        .select_from(TgAccount)
        .where(*scope, TgAccount.status == AccountStatus.healthy.value)
    )
    abnormal = await session.scalar(
        select(func.count())
        .select_from(TgAccount)
        .where(
            *scope,
            TgAccount.status.notin_(
                [
                    AccountStatus.healthy.value,
                    AccountStatus.pending.value,
                    AccountStatus.disabled.value,
                ]
            ),
        )
    )
    new_this_week = await session.scalar(
        select(func.count()).select_from(TgAccount).where(*scope, TgAccount.created_at >= week_ago)
    )
    lease_scope = [] if ids is None else [Lease.account_id.in_(ids)]
    # 在线口径按约定用「未过期租约数」：有租约才说明某个 Worker 正挂着这个号
    active_leases = await session.scalar(
        select(func.count()).select_from(Lease).where(Lease.lease_until > now, *lease_scope)
    )
    return AccountSummary(
        total=int(total or 0),
        healthy=int(healthy or 0),
        abnormal=int(abnormal or 0),
        new_this_week=int(new_this_week or 0),
        online=int(active_leases or 0),
        leased=int(active_leases or 0),
    )


def _login_step(account: TgAccount) -> str:
    """登录进度：API 只写任务，真正执行在 Worker，所以按该号当前落库状态推断步骤。"""
    account_status = enum_value(account.status)
    if account_status == AccountStatus.healthy.value and account.session_enc:
        return "done"
    blob = f"{account.status_reason or ''} {account.last_error or ''}"
    if any(key in blob for key in ("两步", "2FA", "password", "密码")):
        return "password_required"
    return "code_required"


# ---------------- 列表 / 汇总 ----------------

@router.get("", response_model=AccountListResponse, summary="账号列表（含筛选与汇总）")
async def list_accounts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    group_id: Optional[uuid.UUID] = Query(default=None),
    status_filter: Optional[AccountStatus] = Query(default=None, alias="status"),
    current_task: Optional[CurrentTask] = Query(default=None),
    phone: Optional[str] = Query(default=None, description="按脱敏手机号模糊匹配"),
    keyword: Optional[str] = Query(default=None, description="手机号 / 用户名 / 显示名模糊匹配"),
    sort: Optional[str] = Query(default=None, description="排序字段，见 ACCOUNT_SORT_FIELDS"),
    order: Optional[str] = Query(default=None, description="asc | desc，默认 desc"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> AccountListResponse:
    """operator 只看分配到的号；筛选条件与汇总口径保持一致。"""
    ids = await visible_account_ids(session, user)

    conditions = []
    clause = scope_clause(TgAccount.id, ids)
    if clause is not None:
        conditions.append(clause)
    if group_id is not None:
        conditions.append(TgAccount.group_id == group_id)
    if status_filter is not None:
        conditions.append(TgAccount.status == status_filter)
    if current_task is not None:
        conditions.append(TgAccount.current_task == current_task)
    # phone 与 keyword 都是「手机号 / 用户名 / 显示名」模糊匹配，phone 只是语义更明确的名字
    for raw in (phone, keyword):
        if not raw or not raw.strip():
            continue
        pattern = f"%{raw.strip()}%"
        conditions.append(
            or_(
                TgAccount.phone_masked.ilike(pattern),
                TgAccount.username.ilike(pattern),
                TgAccount.display_name.ilike(pattern),
            )
        )

    total = await session.scalar(
        select(func.count()).select_from(TgAccount).where(*conditions)
    )
    order_by = build_order_by(
        sort=sort,
        order=order,
        mapping=ACCOUNT_SORT_FIELDS,
        default_field="created_at",
        default_order="desc",
        tiebreaker=TgAccount.id,
    )
    rows = await session.scalars(
        select(TgAccount)
        .where(*conditions)
        .order_by(*order_by)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    accounts = list(rows.all())
    lease_map = await leases.lease_holders(session, [item.id for item in accounts])

    return AccountListResponse(
        items=[account_out(item, lease_map.get(item.id)) for item in accounts],
        total=int(total or 0),
        page=page,
        page_size=page_size,
        summary=await _summary(session, ids),
    )


@router.get("/summary", response_model=AccountSummary, summary="账号汇总")
async def account_summary(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> AccountSummary:
    """账号管理页顶部四块数字。"""
    return await _summary(session, await visible_account_ids(session, user))


# ---------------- 建档 / 详情 / 修改 ----------------

@router.post("", response_model=AccountOut, status_code=status.HTTP_201_CREATED, summary="账号建档")
async def create_account(
    payload: AccountCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> AccountOut:
    """只建档，不自动登录（登录走 /accounts/login/start）。手机号重复直接 409。"""
    exists = await _find_by_phone(session, payload.phone)
    if exists is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"该手机号已建档：{exists.phone_masked}，请直接使用这个账号",
        )
    await _validate_refs(session, payload.group_id, payload.proxy_id)

    account = TgAccount(
        phone_enc=security.encrypt_secret(payload.phone),
        phone_masked=security.mask_phone(payload.phone),
        group_id=payload.group_id,
        proxy_id=payload.proxy_id,
        remark=payload.remark or "",
        status=AccountStatus.pending,
        current_task=CurrentTask.idle,
        last_error="",
    )
    session.add(account)
    await session.flush()
    await write_audit(
        session,
        action="account.create",
        user_id=user.id,
        account_id=account.id,
        target_type="account",
        target_id=str(account.id),
        detail={"phone_masked": account.phone_masked},
    )
    await session.commit()
    logger.info("账号建档 account_id=%s phone=%s", account.id, account.phone_masked)
    return account_out(await _reload_account(session, account.id))


@router.get("/{account_id}", response_model=AccountOut, summary="账号详情")
async def get_account(
    account_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> AccountOut:
    """越权访问未分配的号一律 403。"""
    await assert_account_access(session, user, account_id)
    account = await _load_account(session, account_id)
    lease_map = await leases.lease_holders(session, [account.id])
    return account_out(account, lease_map.get(account.id))


@router.get("/{account_id}/overview", response_model=AccountOverviewOut, summary="账号详情聚合（右侧抽屉）")
async def account_overview(
    account_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> AccountOverviewOut:
    """一次给出抽屉需要的全部数据：账号 + 分组 / 代理 + 租约 + 统计 + 最近若干行明细。

    越权访问未分配的号一律 403，账号不存在 404。明细只给「最近 N 条」
    （`OVERVIEW_*_LIMIT`），翻更早的历史请用各自的列表接口，避免抽屉变成全表扫描。
    """
    await assert_account_access(session, user, account_id)
    account = await _load_account(session, account_id)
    now = utcnow()

    # ---- 租约 ----
    lease_row = await session.scalar(select(Lease).where(Lease.account_id == account.id))
    lease_out: Optional[LeaseDetail] = None
    if lease_row is not None:
        lease_out = LeaseDetail(
            worker_id=lease_row.worker_id,
            lease_until=lease_row.lease_until,
            last_heartbeat=lease_row.last_heartbeat,
            active=bool(lease_row.lease_until and lease_row.lease_until > now),
        )

    # ---- 分组 / 代理（AccountOut 里只有名字和 endpoint，抽屉要完整对象）----
    group = unloaded_attr(account, "group")
    proxy = unloaded_attr(account, "proxy")
    group_item = None
    if isinstance(group, AccountGroup):
        group_count = await session.scalar(
            select(func.count()).select_from(TgAccount).where(TgAccount.group_id == group.id)
        )
        group_item = group_out(group, int(group_count or 0))
    proxy_item = None
    if isinstance(proxy, Proxy):
        proxy_count = await session.scalar(
            select(func.count()).select_from(TgAccount).where(TgAccount.proxy_id == proxy.id)
        )
        proxy_item = proxy_out(proxy, int(proxy_count or 0))

    # ---- 会话统计 ----
    dialog_stats = DialogStats()
    dialog_rows = await session.execute(
        select(Dialog.kind, func.count()).where(Dialog.account_id == account.id).group_by(Dialog.kind)
    )
    for kind_value, count in dialog_rows.all():
        amount = int(count or 0)
        dialog_stats.total += amount
        label = enum_value(kind_value)
        if label == DialogKind.group.value:
            dialog_stats.group = amount
        elif label == DialogKind.private.value:
            dialog_stats.private = amount
    dialog_stats.unread = int(
        await session.scalar(
            select(func.count())
            .select_from(Dialog)
            .where(Dialog.account_id == account.id, Dialog.unread_count > 0)
        )
        or 0
    )

    # ---- 任务统计（按状态分桶，缺的保持 0）----
    task_stats = TaskStats()
    task_rows = await session.execute(
        select(Task.status, func.count()).where(Task.account_id == account.id).group_by(Task.status)
    )
    for status_value, count in task_rows.all():
        label = enum_value(status_value)
        if hasattr(task_stats, label):
            setattr(task_stats, label, int(count or 0))

    # ---- 最近明细 ----
    dialogs = list(
        (
            await session.scalars(
                select(Dialog)
                .where(Dialog.account_id == account.id)
                .order_by(Dialog.last_message_at.desc().nullslast(), Dialog.created_at.desc())
                .limit(OVERVIEW_DIALOG_LIMIT)
            )
        ).all()
    )
    dialog_ids = select(Dialog.id).where(Dialog.account_id == account.id)
    messages = list(
        (
            await session.scalars(
                select(Message)
                .where(Message.dialog_id.in_(dialog_ids))
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(OVERVIEW_MESSAGE_LIMIT)
            )
        ).all()
    )
    tasks = list(
        (
            await session.scalars(
                select(Task)
                .where(Task.account_id == account.id)
                .order_by(Task.created_at.desc())
                .limit(OVERVIEW_TASK_LIMIT)
            )
        ).all()
    )
    audit_rows = list(
        (
            await session.scalars(
                select(AuditLog)
                .where(AuditLog.account_id == account.id)
                .order_by(AuditLog.created_at.desc())
                .limit(OVERVIEW_AUDIT_LIMIT)
            )
        ).all()
    )
    audit_user_ids = {item.user_id for item in audit_rows if item.user_id}
    auditors = {
        row.id: row
        for row in (await session.scalars(select(User).where(User.id.in_(audit_user_ids)))).all()
    } if audit_user_ids else {}

    audit_items: List[AuditOut] = []
    for log in audit_rows:
        item = AuditOut.model_validate(log)
        item.action_label = ACTION_LABELS.get(log.action, log.action)
        item.user_name = user_label(auditors.get(log.user_id)) if log.user_id else None
        item.account_label = account.phone_masked
        audit_items.append(item)

    lease_hint = (
        {"worker_id": lease_row.worker_id, "lease_until": lease_row.lease_until} if lease_row else None
    )
    return AccountOverviewOut(
        account=account_out(account, lease_hint),
        group=group_item,
        proxy=proxy_item,
        lease=lease_out,
        dialog_stats=dialog_stats,
        task_stats=task_stats,
        recent_dialogs=[dialog_out(item) for item in dialogs],
        recent_messages=[message_out(item) for item in messages],
        recent_tasks=[task_out(item, account) for item in tasks],
        recent_audit=audit_items,
        generated_at=now,
    )


@router.patch("/{account_id}", response_model=AccountOut, summary="修改账号（分组 / 代理 / 备注 / 显示名 / 状态）")
async def update_account(
    account_id: uuid.UUID,
    payload: AccountUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> AccountOut:
    """状态只允许改成 disabled（停用）或 healthy（启用），其余状态由 Worker 按实况写回。

    group_id / proxy_id 传显式 null 表示**解绑**（用 exclude_unset 区分「没传」和「传了 null」）；
    remark / display_name 是不可空的文本字段，null 一律当「没改」。
    """
    await assert_account_access(session, user, account_id)
    account = await _load_account(session, account_id)

    if payload.status is not None and payload.status not in (
        AccountStatus.disabled,
        AccountStatus.healthy,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="状态只能改为 disabled（停用）或 healthy（启用），其它状态由 Worker 按实况写回",
        )

    # exclude_unset：只有请求里真的出现过的字段才算「要改」，null 是有效的解绑指令
    provided = payload.model_dump(exclude_unset=True)
    target_group = payload.group_id if "group_id" in provided else account.group_id
    target_proxy = payload.proxy_id if "proxy_id" in provided else account.proxy_id
    if target_group is not None or target_proxy is not None:
        await _validate_refs(session, target_group, target_proxy)

    changes: dict = {}
    for field in ("group_id", "proxy_id"):
        if field in provided:
            value = provided[field]
            setattr(account, field, value)
            changes[field] = str(value) if value is not None else None
    for field in ("remark", "display_name"):
        value = provided.get(field)
        if value is not None:
            setattr(account, field, value)
            changes[field] = value
    if payload.status is not None:
        account.status = payload.status
        changes["status"] = payload.status.value
        if payload.status == AccountStatus.disabled:
            account.current_task = CurrentTask.idle
            await leases.release_account(session, account_id=account.id)
        elif payload.status == AccountStatus.healthy:
            account.last_error = ""

    await write_audit(
        session,
        action="account.update",
        user_id=user.id,
        account_id=account.id,
        target_type="account",
        target_id=str(account.id),
        detail=changes,
    )
    await session.commit()
    return account_out(await _reload_account(session, account.id))


@router.post("/{account_id}/disable", summary="停用账号并清掉租约")
async def disable_account(
    account_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """号异常时只停它自己：清租约让 Worker 主动断开，不动其它号。"""
    await assert_account_access(session, user, account_id)
    account = await _load_account(session, account_id)
    account.status = AccountStatus.disabled
    account.current_task = CurrentTask.idle
    released = await leases.release_account(session, account_id=account.id)
    await write_audit(
        session,
        action="account.disable",
        user_id=user.id,
        account_id=account.id,
        target_type="account",
        target_id=str(account.id),
        detail={"released_lease": released},
    )
    await session.commit()
    return {"ok": True, "message": "已停用该账号并清除租约" if released else "已停用该账号（原本没有租约）"}


@router.post("/{account_id}/enable", summary="启用账号")
async def enable_account(
    account_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """有会话的号直接回到 healthy；没会话的回到 pending，等 Worker 重新登录。"""
    await assert_account_access(session, user, account_id)
    account = await _load_account(session, account_id)
    target = AccountStatus.healthy if account.session_enc else AccountStatus.pending
    account.status = target
    account.last_error = ""
    await write_audit(
        session,
        action="account.enable",
        user_id=user.id,
        account_id=account.id,
        target_type="account",
        target_id=str(account.id),
        detail={"status": target.value},
    )
    await session.commit()
    message = (
        "已启用，Worker 会在下一轮续租时接管"
        if target == AccountStatus.healthy
        else "该号还没有会话，已回到待登录，请从「登录」发起验证码"
    )
    return {"ok": True, "message": message}


@router.delete("/{account_id}", summary="删除账号")
async def delete_account(
    account_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """物理删除；会话、消息、任务、租约、分配都靠外键级联清掉，审计行保留（account_id 置空）。"""
    await assert_account_access(session, user, account_id)
    account = await _load_account(session, account_id)
    masked = account.phone_masked
    await write_audit(
        session,
        action="account.update",
        user_id=user.id,
        target_type="account",
        target_id=str(account.id),
        detail={"deleted": True, "phone_masked": masked},
    )
    await leases.release_account(session, account_id=account.id)
    await session.delete(account)
    await session.commit()
    logger.info("账号已删除 account_id=%s phone=%s", account_id, masked)
    return {"ok": True, "message": f"已删除账号 {masked}"}


@router.post("/{account_id}/release-lease", summary="只清这个号的租约")
async def release_lease(
    account_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """单号异常时用：清掉租约，其它号不受影响。"""
    await assert_account_access(session, user, account_id)
    account = await _load_account(session, account_id)
    holders = await leases.lease_holders(session, [account.id])
    holder = holders.get(account.id)
    released = await leases.release_account(session, account_id=account.id)
    await write_audit(
        session,
        action="account.release_lease",
        user_id=user.id,
        account_id=account.id,
        target_type="account",
        target_id=str(account.id),
        detail={"previous_worker_id": (holder or {}).get("worker_id")},
    )
    await session.commit()
    return {
        "ok": True,
        "message": f"已清除租约（原持有者 {holder['worker_id']}）" if holder else "该号当前没有租约",
    }


# ---------------- 任务类动作 ----------------

@router.post("/{account_id}/sync-dialogs", summary="同步该号的会话列表")
async def sync_dialogs(
    account_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """写一条 sync_dialogs 任务，Worker 拉到群和私信后写 dialogs 表。"""
    await assert_account_access(session, user, account_id)
    account = await _load_account(session, account_id)
    task = await enqueue_task(
        session,
        type=TaskType.sync_dialogs,
        account_id=account.id,
        payload={},
        created_by=user.id,
        priority=60,
    )
    await write_audit(
        session,
        action="dialog.sync",
        user_id=user.id,
        account_id=account.id,
        target_type="account",
        target_id=str(account.id),
        detail={"task_id": str(task.id)},
    )
    await session.commit()
    await publish_task_safely(
        {"task_id": str(task.id), "type": enum_value(task.type), "ok": True, "detail": "已入队"}
    )
    return {"ok": True, "message": "已排队同步会话，等持有租约的 Worker 执行", "task_id": task.id}


@router.post("/{account_id}/profile", summary="修改本号名称 / 头像")
async def update_profile(
    account_id: uuid.UUID,
    payload: ProfileUpdateRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """资料改动由 Worker 用该号自己的会话调 Telegram，API 只入队。"""
    await assert_account_access(session, user, account_id)
    account = await _load_account(session, account_id)
    data = {key: value for key, value in payload.model_dump().items() if value is not None}
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="没有要修改的字段")
    task = await enqueue_task(
        session,
        type=TaskType.update_profile,
        account_id=account.id,
        payload=data,
        created_by=user.id,
        priority=70,
    )
    await write_audit(
        session,
        action="account.profile_update",
        user_id=user.id,
        account_id=account.id,
        target_type="account",
        target_id=str(account.id),
        detail={"task_id": str(task.id), **data},
    )
    await session.commit()
    return {"ok": True, "message": "已排队修改资料，等 Worker 执行", "task_id": task.id}


# ---------------- 登录三步 ----------------

@router.post("/login/start", response_model=LoginStepResponse, summary="登录第一步：发验证码")
async def login_start(
    payload: LoginStartRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> LoginStepResponse:
    """没传 account_id 时先建档（手机号重复则复用已有账号），再写 login_start 任务。

    已有号重新登录只传 account_id 即可：手机号从库里加密保存的 phone_enc 解出来，
    值班的人不用对着脱敏号（861****2551）重敲一遍。
    """
    if payload.account_id is not None:
        await assert_account_access(session, user, payload.account_id)
        account = await _load_account(session, payload.account_id)
        if payload.group_id is not None or payload.proxy_id is not None:
            await _validate_refs(
                session,
                payload.group_id if payload.group_id is not None else account.group_id,
                payload.proxy_id if payload.proxy_id is not None else account.proxy_id,
            )
            if payload.group_id is not None:
                account.group_id = payload.group_id
            if payload.proxy_id is not None:
                account.proxy_id = payload.proxy_id
    else:
        await _validate_refs(session, payload.group_id, payload.proxy_id)
        account = await _find_by_phone(session, payload.phone)
        if account is None:
            account = TgAccount(
                phone_enc=security.encrypt_secret(payload.phone),
                phone_masked=security.mask_phone(payload.phone),
                group_id=payload.group_id,
                proxy_id=payload.proxy_id,
                status=AccountStatus.pending,
                current_task=CurrentTask.idle,
                last_error="",
            )
            session.add(account)
            await session.flush()
            logger.info("登录时自动建档 account_id=%s phone=%s", account.id, account.phone_masked)
        else:
            # 复用已有号：只补分组 / 代理，不动状态
            await assert_account_access(session, user, account.id)
            if payload.group_id is not None:
                account.group_id = payload.group_id
            if payload.proxy_id is not None:
                account.proxy_id = payload.proxy_id

    phone = payload.phone
    if not phone and account.phone_enc:
        try:
            phone = security.decrypt_secret(account.phone_enc)
        except ValueError:
            phone = None
    if not phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="这个号没有可用的手机号记录，请重新填写完整手机号再发起登录",
        )

    task = await enqueue_task(
        session,
        type=TaskType.login_start,
        account_id=account.id,
        payload={"phone": phone},
        created_by=user.id,
        priority=10,
    )
    await write_audit(
        session,
        action="account.login_start",
        user_id=user.id,
        account_id=account.id,
        target_type="account",
        target_id=str(account.id),
        detail={"phone_masked": account.phone_masked, "task_id": str(task.id)},
    )
    await session.commit()
    return LoginStepResponse(
        account_id=account.id,
        step="code_required",
        message="已排队发送验证码，验证码只会发到这个号自己的 Telegram 客户端",
        task_id=task.id,
    )


@router.post("/login/code", response_model=LoginStepResponse, summary="登录第二步：提交验证码")
async def login_code(
    payload: LoginCodeRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> LoginStepResponse:
    """提交验证码；开了两步验证的号，下一步会返回 password_required。"""
    await assert_account_access(session, user, payload.account_id)
    account = await _load_account(session, payload.account_id)
    task = await enqueue_task(
        session,
        type=TaskType.login_code,
        account_id=account.id,
        payload={"code": payload.code},
        created_by=user.id,
        priority=10,
    )
    await write_audit(
        session,
        action="account.login_code",
        user_id=user.id,
        account_id=account.id,
        target_type="account",
        target_id=str(account.id),
        detail={"task_id": str(task.id)},
    )
    await session.commit()
    step = _login_step(account)
    message = {
        "done": "登录完成，会话已写回该账号",
        "password_required": "该号开启了两步验证，请继续提交两步密码",
        "code_required": "验证码已提交，等待 Worker 完成登录",
    }.get(step, "验证码已提交")
    return LoginStepResponse(account_id=account.id, step=step, message=message, task_id=task.id)


@router.post("/login/password", response_model=LoginStepResponse, summary="登录第三步：提交两步验证密码")
async def login_password(
    payload: LoginPasswordRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> LoginStepResponse:
    """两步密码只用于这一次登录（payload 落库由 Worker 消费后即失效）。"""
    await assert_account_access(session, user, payload.account_id)
    account = await _load_account(session, payload.account_id)
    task = await enqueue_task(
        session,
        type=TaskType.login_password,
        account_id=account.id,
        payload={"password": payload.password},
        created_by=user.id,
        priority=10,
    )
    await write_audit(
        session,
        action="account.login_password",
        user_id=user.id,
        account_id=account.id,
        target_type="account",
        target_id=str(account.id),
        detail={"task_id": str(task.id)},
    )
    await session.commit()
    # 两步密码是操作者要提交的最后一步：接口这一侧就算走完（会话由 Worker 随后写回），
    # 所以回 done，前端可以关掉登录弹窗、刷新账号列表看状态。
    logger.info("已提交两步密码 account_id=%s task_id=%s", account.id, task.id)
    return LoginStepResponse(
        account_id=account.id,
        step="done",
        message="两步密码已提交，Worker 完成后会把加密会话写回该账号（可刷新列表查看状态）",
        task_id=task.id,
    )


# ---------------- 检测 ----------------

async def _check_one(
    session: AsyncSession, user: User, account: TgAccount, now=None
) -> CheckResultOut:
    """写一条 account_check 任务 + 续一次租约，并立刻按当前状态回答「连得上吗」。"""
    now = now or utcnow()
    # 已经有排队中的检测就复用，避免值班的人连点把任务表刷满
    task = await session.scalar(
        select(Task)
        .where(
            Task.account_id == account.id,
            Task.type == TaskType.account_check,
            Task.status.in_([TaskStatus.pending, TaskStatus.running]),
        )
        .order_by(Task.created_at.desc())
        .limit(1)
    )
    if task is None:
        task = await enqueue_task(
            session,
            type=TaskType.account_check,
            account_id=account.id,
            payload={},
            created_by=user.id,
            priority=80,
        )
    await session.flush()

    # 告诉 Worker「这个号现在就要检一次」，并顺手把有效租约续上，
    # 否则租约一过期这个任务就没人能领（Worker 只领自己租约内的号）。
    try:
        await events.request_account_check(get_redis(), account.id)
    except Exception:  # noqa: BLE001 - Redis 抖动不影响任务入队
        logger.warning("写检测请求标记到 Redis 失败 account_id=%s", account.id, exc_info=True)

    lease_map = await leases.lease_holders(session, [account.id])
    holder = lease_map.get(account.id)
    if holder and holder.get("lease_until") and holder["lease_until"] > now:
        await leases.renew_leases(session, worker_id=holder["worker_id"])

    account_status = enum_value(account.status)
    reachable = account_status == AccountStatus.healthy.value and bool(holder)
    if reachable:
        message = f"租约有效（Worker {holder['worker_id']}），已排队重新检测一次"
    elif account_status == AccountStatus.healthy.value:
        message = "状态正常但没有有效租约：暂没有 Worker 接管这个号"
    else:
        label = ACCOUNT_STATUS_LABELS.get(account_status, account_status)
        message = f"当前状态「{label}」，已排队检测；结果会写回该账号"

    return CheckResultOut(
        account_id=account.id,
        phone_masked=account.phone_masked,
        reachable=reachable,
        status=account.status,
        status_label=ACCOUNT_STATUS_LABELS.get(account_status, ""),
        message=message,
        task_id=task.id,
    )


@router.post("/{account_id}/check", response_model=CheckResultOut, summary="单号检测")
async def check_account(
    account_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> CheckResultOut:
    """检测按钮：立刻续一次租约，写一条 account_check 任务，返回当前可达性。"""
    await assert_account_access(session, user, account_id)
    account = await _load_account(session, account_id)
    result = await _check_one(session, user, account)
    await write_audit(
        session,
        action="account.check",
        user_id=user.id,
        account_id=account.id,
        target_type="account",
        target_id=str(account.id),
        detail={"reachable": result.reachable, "task_id": str(result.task_id) if result.task_id else None},
    )
    await session.commit()
    return result


@router.post("/check", response_model=List[CheckResultOut], summary="批量检测（选中 / 全部 / 某个分组）")
async def check_accounts(
    payload: CheckRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> List[CheckResultOut]:
    """scope 支持 selected（配合 account_ids）、all、group:<分组ID>；operator 只会检自己分配到的号。"""
    ids = await visible_account_ids(session, user)
    stmt = select(TgAccount)
    clause = scope_clause(TgAccount.id, ids)
    if clause is not None:
        stmt = stmt.where(clause)

    scope = (payload.scope or "selected").strip()
    if payload.account_ids:
        wanted = set(payload.account_ids)
        allowed = set(ids) if ids is not None else None
        if allowed is not None:
            forbidden = wanted - allowed
            if forbidden:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"有账号未分配给你：{', '.join(str(item) for item in sorted(forbidden, key=str))}",
                )
        stmt = stmt.where(TgAccount.id.in_(list(wanted)))
    elif scope == "all":
        pass
    elif scope.startswith("group"):
        raw = scope.split(":", 1)[1].strip() if ":" in scope else ""
        group_id = None
        try:
            group_id = uuid.UUID(raw)
        except (ValueError, AttributeError):
            group_id = None
        if group_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="scope 要写成 group:<分组ID>",
            )
        stmt = stmt.where(TgAccount.group_id == group_id)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="scope 只能是 selected / all / group:<分组ID>",
        )

    accounts = list((await session.scalars(stmt.order_by(TgAccount.created_at.asc()).limit(MAX_CHECK_BATCH + 1))).all())
    if len(accounts) > MAX_CHECK_BATCH:
        logger.warning("批量检测超过上限，只处理前 %s 个", MAX_CHECK_BATCH)
        accounts = accounts[:MAX_CHECK_BATCH]

    now = utcnow()
    results = [await _check_one(session, user, account, now) for account in accounts]
    await write_audit(
        session,
        action="account.check",
        user_id=user.id,
        target_type="account_batch",
        target_id=scope,
        detail={"count": len(results), "scope": scope},
    )
    await session.commit()
    return results
