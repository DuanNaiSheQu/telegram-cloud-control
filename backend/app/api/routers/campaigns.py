"""营销中心：批量私信 / 群发 / 素材群发 / 加群 / 退群 / 强拉进群 / 批量改资料 / 吵群 / 拟人发言。

架构：每次提交生成一个 `batch_id`（UUID），按「一个号一条任务」写 tasks 表，
Worker 按租约认领执行；`GET /campaigns/batches` 按 batch_id 聚合进度。
提交即返回逐账号回执（复用 BulkResultResponse），执行结果在任务中心 / 批次详情看。

安全与节奏：
- 账号选择器复用 BulkScopeRequest：operator 的 all 只覆盖分配给他的号，点名越权 403；
- 相邻两个号的首发时间按 campaign_stagger_seconds 错开，避免一批号同时在线；
- 吵群 / 拟人的轮数与间隔在 schema 层就按配置上限校验。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, visible_account_ids
from app.api.routers.accounts_bulk import scope_clause
from app.api.routers import enum_value, publish_task_safely
from app.api.routers.accounts_bulk import _resolve_accounts
from app.api.routers.tasks import CANCELLABLE_STATUSES
from app.config import settings
from app.core.audit import write_audit
from app.core.tasks import cancel_task, enqueue_task
from app.models import (
    TASK_STATUS_LABELS,
    TASK_TYPE_LABELS,
    Material,
    Task,
    TaskStatus,
    TaskType,
    TgAccount,
    User,
    AccountStatus,
    Bot,
)
from app.schemas import (
    BulkAccountResult,
    BulkPmRequest,
    BulkResultResponse,
    CampaignBatchItem,
    CampaignBatchListResponse,
    CampaignBatchOut,
    ForceAddRequest,
    GroupBroadcastRequest,
    JoinGroupRequest,
    LeaveGroupRequest,
    MaterialSendRequest,
    PersonaRequest,
    ProfileBulkRequest,
    StormRequest,
)
from app.schemas.campaign import GenerateTextsRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _item(account: TgAccount, ok: bool = True, message: str = "", task_id: Optional[uuid.UUID] = None) -> BulkAccountResult:
    return BulkAccountResult(
        account_id=account.id,
        account_label=account.phone_masked or str(account.id)[:8],
        ok=ok,
        message=message,
        task_id=task_id,
    )


def _split_round_robin(targets: list[str], index: int, count: int) -> list[str]:
    """把目标按账号轮询切分：`round_robin` 模式下每个目标只交给一个号。

    比「每个号都把全部目标发一遍」更像真人分头干活，也避免同一个目标被多个号连续打扰。
    """
    if count <= 1 or not targets:
        return list(targets)
    step = max(1, count)
    return [target for position, target in enumerate(targets) if position % step == index]


async def _ensure_material(session: AsyncSession, material_id) -> None:
    """带素材的批量动作：入队前就把「素材不存在」拦掉，别等 Worker 跑起来才报错。"""
    if not material_id:
        return
    material = await session.get(Material, material_id)
    if material is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="素材不存在（可能已被删除）")


#: 自动补号：默认补到多少个号（目标本身有限，补太多没意义）
AUTO_SUPPLY_DEFAULT = 10
#: 补号上限：一次最多用多少个号承担一批目标，避免把号池全拉起来
AUTO_SUPPLY_MAX = 50


async def _auto_supply_accounts(
    session: AsyncSession, user: User, accounts: List[TgAccount], *, need: int
) -> List[TgAccount]:
    """号不够时从号池补位：只挑**状态正常、有会话、且不在现有列表里**的号。

    补进来的号同样受节流与每日配额约束（执行侧门禁对每个号独立生效），
    所以「补号」只是让任务跑得更快，不会让某个号超发。
    """
    target = max(1, min(int(need), AUTO_SUPPLY_MAX))
    if len(accounts) >= target:
        return accounts
    existing = {item.id for item in accounts}
    conditions = [
        TgAccount.status == AccountStatus.healthy,
        TgAccount.session_enc.is_not(None),
    ]
    if existing:
        conditions.append(TgAccount.id.notin_(existing))
    visible = await visible_account_ids(session, user)
    clause = scope_clause(TgAccount.id, visible)
    if clause is not None:
        conditions.append(clause)
    extra = list(
        (
            await session.scalars(
                select(TgAccount)
                .where(*conditions)
                .order_by(TgAccount.last_heartbeat.desc().nulls_last(), TgAccount.created_at)
                .limit(target - len(accounts))
            )
        ).all()
    )
    if extra:
        logger.info("自动补号：补入 %s 个可用号承担本批目标", len(extra))
    return accounts + extra

async def _submit_campaign(
    *,
    action: str,
    task_type: TaskType,
    payload_scope,
    params: dict,
    session: AsyncSession,
    user: User,
    per_account: Optional[Callable[[TgAccount, int, int], dict]] = None,
    priority: int = 80,
) -> BulkResultResponse:
    """公共提交流程：解析账号范围 → 生成 batch_id → 每号一条任务（错峰入队）→ 审计 + 回执。"""
    accounts, scope, truncated = await _resolve_accounts(session, user, payload_scope, usable_only=True)
    # 无号自动补号：勾了这项、而可用的号不够承担这批目标时，自动从号池里补状态正常的号。
    # 运营不用手动一个个挑——号源少了任务会变慢，这个开关让系统自己把坑填上。
    if getattr(payload_scope, "auto_supply", False):
        wanted = int(getattr(payload_scope, "auto_supply_target", 0) or 0) or AUTO_SUPPLY_DEFAULT
        accounts = await _auto_supply_accounts(session, user, accounts, need=wanted)
    if not accounts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="没有匹配到账号：请先勾选账号，或用 all / group:<分组ID> 指定范围",
        )
    batch_id = uuid.uuid4()
    items: List[BulkAccountResult] = []
    task_ids: List[uuid.UUID] = []
    stagger = max(0.0, float(settings.campaign_stagger_seconds))
    for index, account in enumerate(accounts):
        payload = {
            **params,
            "batch_id": str(batch_id),
            "account_index": index,
            "account_count": len(accounts),
        }
        if per_account is not None:
            # 第 3 个参数是账号总数：轮询切分需要它才能算出「这个号该拿哪些目标」
            payload.update(per_account(account, index, len(accounts)))
        try:
            task = await enqueue_task(
                session,
                type=task_type,
                account_id=account.id,
                payload=payload,
                created_by=user.id,
                priority=priority,
                run_after=_now() + timedelta(seconds=stagger * index),
            )
            task_ids.append(task.id)
            items.append(_item(account, message=f"已排队（{TASK_TYPE_LABELS.get(task_type.value, task_type.value)}）", task_id=task.id))
        except Exception as exc:  # noqa: BLE001 - 单个号入队失败不影响整批
            logger.warning("批量运营入队失败 action=%s account_id=%s: %s", action, account.id, exc)
            items.append(_item(account, ok=False, message=f"入队失败：{exc}"))

    await write_audit(
        session,
        action=action,
        user_id=user.id,
        target_type="campaign_batch",
        target_id=str(batch_id),
        detail={
            "batch_id": str(batch_id),
            "scope": scope,
            "task_type": task_type.value,
            "count": len(items),
            "truncated": truncated,
        },
    )
    await session.commit()
    await publish_task_safely(
        {"task_id": None, "type": task_type.value, "ok": True, "detail": f"批次 {batch_id} 已排队 {len(task_ids)} 个号"}
    )
    succeeded = sum(1 for item in items if item.ok)
    failed = sum(1 for item in items if not item.ok)
    logger.info("批量运营提交 action=%s batch=%s 成功=%s 失败=%s by=%s", action, batch_id, succeeded, failed, user.username)
    return BulkResultResponse(
        ok=failed == 0,
        action=action,
        message=f"批次 {batch_id}：已排队 {succeeded} 个号" + (f"，失败 {failed} 个" if failed else ""),
        requested=len(accounts),
        succeeded=succeeded,
        failed=failed,
        skipped=0,
        truncated=truncated,
        task_ids=task_ids,
        items=items,
    )


# ---------------- 批量私信 ----------------

@router.post("/bulk-pm", response_model=BulkResultResponse, summary="批量私信：一批号各向目标逐个发消息")
async def bulk_pm(
    payload: BulkPmRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> BulkResultResponse:
    # 多通道分流：选「用 Bot 发送」时不走账号，直接派 Bot 任务。
    # Bot 不受账号冻结 / 每日配额 / 设备指纹影响，代价是只能发给**和它交互过**的用户。
    if payload.via_bot:
        if payload.bot_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用 Bot 发送时必须选择 bot_id")
        bot = await session.get(Bot, payload.bot_id)
        if bot is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot 不存在")
        text = (payload.text or "").strip() or (payload.texts[0] if payload.texts else "")
        if not text:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用 Bot 发送同样需要文本或文本池")
        task = await enqueue_task(
            session,
            type=TaskType.bot_broadcast,
            bot_id=bot.id,
            payload={"targets": payload.targets, "text": text, "source": "bulk_pm_via_bot"},
            created_by=user.id,
            priority=70,
        )
        await write_audit(
            session,
            action="campaign.bulk_pm_via_bot",
            user_id=user.id,
            target_type="bot",
            target_id=str(bot.id),
            detail={"targets": len(payload.targets)},
        )
        await session.commit()
        return BulkResultResponse(
            ok=True,
            action="bulk_pm_via_bot",
            message=(
                f"已排队：用 @{bot.bot_username or bot.name} 给 {len(payload.targets)} 个目标发私信。"
                "注意 Bot 只能给与它交互过的用户发消息，陌生人会失败（Telegram 限制）。"
            ),
            requested=len(payload.targets),
            succeeded=1,
            failed=0,
            skipped=0,
            truncated=False,
            task_ids=[task.id],
            items=[],
        )
    params = {
        "targets": payload.targets,
        "texts": payload.texts,
        "text": payload.text,
        "naturalize": payload.naturalize,
        "min_interval": payload.min_interval,
        "max_interval": payload.max_interval,
        # 可选附带素材：文本作为配文一起发
        "material_id": str(payload.material_id) if payload.material_id else None,
    }
    await _ensure_material(session, payload.material_id)
    round_robin = payload.dispatch == "round_robin"
    return await _submit_campaign(
        action="campaign.bulk_pm",
        task_type=TaskType.bulk_pm,
        payload_scope=payload,
        params={**params, "dispatch": payload.dispatch},
        session=session,
        user=user,
        # 轮询模式：目标切片后每个号只跑自己那份，多号并行分摊
        per_account=(
            (lambda account, index, total: {"targets": _split_round_robin(payload.targets, index, total)})
            if round_robin
            else None
        ),
    )


# ---------------- 群发 ----------------

@router.post("/group-broadcast", response_model=BulkResultResponse, summary="批量群发：一批号各向指定群发一条")
async def group_broadcast(
    payload: GroupBroadcastRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> BulkResultResponse:
    await _ensure_material(session, payload.material_id)
    params = {
        "target_group": payload.target_group.strip(),
        "texts": payload.texts,
        "text": payload.text,
        "naturalize": payload.naturalize,
        "material_id": str(payload.material_id) if payload.material_id else None,
    }
    return await _submit_campaign(
        action="campaign.group_broadcast",
        task_type=TaskType.group_broadcast,
        payload_scope=payload,
        params=params,
        session=session,
        user=user,
    )


@router.post("/material-send", response_model=BulkResultResponse, summary="素材群发：按素材库内容发给指定群或目标")
async def material_send(
    payload: MaterialSendRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> BulkResultResponse:
    material = await session.get(Material, payload.material_id)
    if material is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="素材不存在")
    params = {
        "material_id": str(material.id),
        "target_group": payload.target_group.strip() if payload.target_group else None,
        "targets": payload.targets,
        "min_interval": payload.min_interval,
        "max_interval": payload.max_interval,
    }
    return await _submit_campaign(
        action="campaign.material_send",
        task_type=TaskType.material_send,
        payload_scope=payload,
        params={**params, "dispatch": payload.dispatch},
        session=session,
        user=user,
        # 轮询模式：目标列表按账号切片，多号并行分摊
        per_account=(
            (lambda account, index, total: {"targets": _split_round_robin(payload.targets or [], index, total)})
            if payload.dispatch == "round_robin" and payload.targets
            else None
        ),
    )


# ---------------- 加群 / 退群 / 强拉 ----------------

@router.post("/join-group", response_model=BulkResultResponse, summary="批量加群：邀请链接或公开群")
async def join_group(
    payload: JoinGroupRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> BulkResultResponse:
    targets = payload.targets or []
    round_robin = payload.dispatch == "round_robin"
    return await _submit_campaign(
        action="campaign.join_group",
        task_type=TaskType.join_group,
        payload_scope=payload,
        params={"target": targets[0] if targets else "", "targets": targets, "dispatch": payload.dispatch},
        session=session,
        user=user,
        # 轮询模式：群按账号轮流切分，一个群只由一个号去加（避免所有号都去挤同一个群）
        per_account=(
            (lambda account, index, total: {"targets": _split_round_robin(targets, index, total)})
            if round_robin
            else None
        ),
    )


@router.post("/leave-group", response_model=BulkResultResponse, summary="批量退群")
async def leave_group(
    payload: LeaveGroupRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> BulkResultResponse:
    return await _submit_campaign(
        action="campaign.leave_group",
        task_type=TaskType.leave_group,
        payload_scope=payload,
        params={
            "target": (payload.targets or [""])[0],
            "targets": payload.targets,
            "delete_history": payload.delete_history,
            "dispatch": payload.dispatch,
        },
        session=session,
        user=user,
    )


@router.post("/force-add", response_model=BulkResultResponse, summary="强拉进群：把成员拉进群（执行号须为管理员）")
async def force_add(
    payload: ForceAddRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> BulkResultResponse:
    return await _submit_campaign(
        action="campaign.force_add",
        task_type=TaskType.force_add_member,
        payload_scope=payload,
        params={
            "group": (payload.groups or [""])[0],
            "groups": payload.groups,
            "members": payload.members,
            "dispatch": payload.dispatch,
        },
        session=session,
        user=user,
    )


# ---------------- 批量改资料 ----------------

@router.post("/profile-update", response_model=BulkResultResponse, summary="批量改资料：一批号统一改名 / 简介 / 头像")
async def profile_update(
    payload: ProfileBulkRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> BulkResultResponse:
    base = payload.profile.clean()

    def per(account: TgAccount, _index: int, _total: int) -> dict:
        merged = dict(base)
        if payload.per_account and account.id in payload.per_account:
            merged.update(payload.per_account[account.id].clean())
        return merged

    pools = {
        "first_name_pool": [s.strip() for s in (payload.first_name_pool or []) if s.strip()],
        "last_name_pool": [s.strip() for s in (payload.last_name_pool or []) if s.strip()],
        "bio_pool": [s.strip() for s in (payload.bio_pool or []) if s.strip()],
        "assign_mode": payload.assign_mode,
        "username_prefix": (payload.username_prefix or "").strip() or None,
        "username_random_digits": payload.username_random_digits,
    }
    if not any(v for k, v in pools.items() if k.endswith("_pool")) and not pools["username_prefix"] and not base:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="没有要改的字段：填统一资料、候选池或用户名前缀其中之一",
        )
    return await _submit_campaign(
        action="campaign.profile_update",
        task_type=TaskType.update_profile,
        payload_scope=payload,
        params={**pools},
        per_account=per,
        session=session,
        user=user,
        priority=70,
    )


# ---------------- 吵群 / 拟人发言 ----------------

@router.post("/storm", response_model=BulkResultResponse, summary="吵群：一批号按文本池和随机间隔连续发言")
async def storm(
    payload: StormRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> BulkResultResponse:
    params = {
        "dialog_id": str(payload.dialog_id) if payload.dialog_id else None,
        "group": payload.group.strip() if payload.group else None,
        "rounds": payload.rounds,
        "min_interval": payload.min_interval,
        "max_interval": payload.max_interval,
        "texts": payload.texts,
        "reply_probability": payload.reply_probability,
    }
    return await _submit_campaign(
        action="campaign.storm",
        task_type=TaskType.storm_chat,
        payload_scope=payload,
        params=params,
        session=session,
        user=user,
        priority=60,
    )


@router.post("/persona", response_model=BulkResultResponse, summary="拟人发言：一批号按人设生成话术连续发言")
async def persona(
    payload: PersonaRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> BulkResultResponse:
    params = {
        "dialog_id": str(payload.dialog_id) if payload.dialog_id else None,
        "group": payload.group.strip() if payload.group else None,
        "persona": payload.persona.strip(),
        "topic": payload.topic.strip() if payload.topic else None,
        "use_ai": payload.use_ai,
        "texts": payload.texts,
        "rounds": payload.rounds,
        "min_interval": payload.min_interval,
        "max_interval": payload.max_interval,
    }
    return await _submit_campaign(
        action="campaign.persona",
        task_type=TaskType.persona_chat,
        payload_scope=payload,
        params=params,
        session=session,
        user=user,
        priority=60,
    )


# ---------------- 批次聚合 ----------------

def _batch_clause(ids: Optional[List[uuid.UUID]]):
    conditions = []
    if ids is not None:
        conditions.append(Task.account_id.in_(ids))
    conditions.append(Task.payload["batch_id"].astext.is_not(None))
    return conditions


def _enrich_batch_item(task: Task, account: Optional[TgAccount]) -> CampaignBatchItem:
    type_value = enum_value(task.type)
    status_value = enum_value(task.status)
    return CampaignBatchItem(
        account_id=task.account_id,
        account_label=account.phone_masked if account else "",
        task_id=task.id,
        type=type_value,
        type_label=TASK_TYPE_LABELS.get(type_value, type_value),
        status=status_value,
        status_label=TASK_STATUS_LABELS.get(status_value, status_value),
        attempts=int(task.attempts or 0),
        error=task.error or "",
        started_at=task.started_at,
        completed_at=task.completed_at,
    )


@router.get("/batches", response_model=CampaignBatchListResponse, summary="批次列表（按 batch_id 聚合）")
async def list_batches(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> CampaignBatchListResponse:
    ids = await visible_account_ids(session, user)
    scope_sql = ""
    params: dict = {"off": (page - 1) * page_size, "lim": page_size}
    if ids is not None:
        scope_sql = "AND account_id = ANY(:ids)"
        params["ids"] = [str(item) for item in ids]
    # JSONB 聚合用原生 SQL：SQLAlchemy 对 payload->>'batch_id' 的 GROUP BY 渲染会退化
    rows = (
        await session.execute(
            text(
                "SELECT payload->>'batch_id' AS batch_id, count(*) AS total, min(created_at) AS first_created "
                "FROM tasks WHERE payload ? 'batch_id' "
                + scope_sql
                + " GROUP BY 1 ORDER BY min(created_at) DESC OFFSET :off LIMIT :lim"
            ),
            params,
        )
    ).all()
    total = await session.scalar(
        select(func.count()).select_from(
            text("(SELECT 1 FROM tasks WHERE payload ? 'batch_id' " + scope_sql + " GROUP BY payload->>'batch_id') AS batches")
        ),
        params,
    )
    return CampaignBatchListResponse(
        items=[
            CampaignBatchOut(
                batch_id=uuid.UUID(row.batch_id),
                created_at=row.first_created,
                total=int(row.total or 0),
            )
            for row in rows
        ],
        total=int(total or 0),
        page=page,
        page_size=page_size,
    )


@router.get("/batches/{batch_id}", response_model=CampaignBatchOut, summary="批次详情（逐号状态）")
async def get_batch(
    batch_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> CampaignBatchOut:
    ids = await visible_account_ids(session, user)
    conditions = _batch_clause(ids)
    conditions.append(Task.payload["batch_id"].astext == str(batch_id))
    tasks = list((await session.scalars(select(Task).where(*conditions).order_by(Task.created_at.asc()))).all())
    if not tasks:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="批次不存在或不属于你的账号")
    account_ids = {item.account_id for item in tasks if item.account_id}
    accounts = {
        row.id: row
        for row in (await session.scalars(select(TgAccount).where(TgAccount.id.in_(account_ids)))).all()
    } if account_ids else {}
    counts = {item.value: 0 for item in TaskStatus}
    items: List[CampaignBatchItem] = []
    for task in tasks:
        status_value = enum_value(task.status)
        counts[status_value] = counts.get(status_value, 0) + 1
        items.append(_enrich_batch_item(task, accounts.get(task.account_id)))
    return CampaignBatchOut(
        batch_id=batch_id,
        created_at=tasks[0].created_at,
        total=len(tasks),
        counts=counts,
        items=items,
    )


@router.post("/batches/{batch_id}/cancel", summary="取消批次（待执行 / 等待确认 / 执行中的任务）")
async def cancel_batch(
    batch_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> BulkResultResponse:
    ids = await visible_account_ids(session, user)
    conditions = _batch_clause(ids)
    conditions.append(Task.payload["batch_id"].astext == str(batch_id))
    tasks = list((await session.scalars(select(Task).where(*conditions))).all())
    if not tasks:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="批次不存在或不属于你的账号")
    cancelled = 0
    for task in tasks:
        if task.status in CANCELLABLE_STATUSES:
            await cancel_task(session, task)
            cancelled += 1
    await write_audit(
        session,
        action="campaign.batch_cancel",
        user_id=user.id,
        target_type="campaign_batch",
        target_id=str(batch_id),
        detail={"total": len(tasks), "cancelled": cancelled},
    )
    await session.commit()
    await publish_task_safely({"task_id": None, "type": "", "ok": False, "detail": f"批次 {batch_id} 已取消 {cancelled} 条任务"})
    logger.info("取消批次 batch=%s 取消=%s by=%s", batch_id, cancelled, user.username)
    return BulkResultResponse(
        ok=True,
        action="cancel",
        message=f"批次 {batch_id}：共 {len(tasks)} 条任务，已取消 {cancelled} 条（其余为已完成 / 失败状态）",
        requested=len(tasks),
        succeeded=cancelled,
        failed=0,
        skipped=len(tasks) - cancelled,
    )


@router.post("/generate-texts", summary="AI 生成一批话术（按主题与风格）")
async def generate_texts(
    payload: GenerateTextsRequest,
    user: User = Depends(get_current_user),
) -> dict:
    """让 AI 按主题生成 N 条互不相同的话术，填进文本池。

    设计意图：运营要的是「每次发出去的话不一样，但都在我能接受的范围内」——
    先一次性生成一批**受控**话术，再由发送端逐条取用；
    而不是让模型每次发送时自由发挥（那会跑偏到无法预期的内容）。
    """
    from app.services import ai

    if not ai.available:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "AI 未启用：请在 backend/.env 配置 AI_ENABLED=true、AI_API_KEY、AI_BASE_URL、AI_MODEL"
                "（OpenAI 兼容接口，DeepSeek / 通义 / 本地 vLLM 都行），改完重启后端。"
            ),
        )
    prompt = (
        f"请围绕主题「{payload.topic}」，用{payload.language}写出 {payload.count} 条互不相同的短消息。"
        f"语气要求：{payload.style}。要求：每条独立成行，行首不要序号与引号；"
        "长度 40 字以内，像真人随手发的；不要模板腔，最多一个 emoji；直接输出这些消息，不要解释。"
    )
    raw = await ai.chat(
        [
            {"role": "system", "content": "你是资深社群运营，擅长写不同口吻的短消息。"},
            {"role": "user", "content": prompt},
        ],
        temperature=1.0,
    )
    import re as _re

    texts: list[str] = []
    for line in (raw or "").splitlines():
        item = line.strip()
        if not item:
            continue
        item = _re.sub(r"^[0-9]+[.、)]\s*", "", item)
        item = item.strip('"\'“”「」 ')
        if 1 < len(item) <= 200:
            texts.append(item)
    texts = list(dict.fromkeys(texts))[: payload.count]
    if not texts:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="AI 没有返回可用文本，请稍后重试或换个主题")
    return {"texts": texts}
