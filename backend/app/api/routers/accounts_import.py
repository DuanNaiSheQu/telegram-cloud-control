"""账号矩阵导入：手机号清单 / Session 串 / .session 文件 / tdata 目录，四种入口一次讲清。

路由挂在 `/api/accounts/import`，必须在 `accounts.router` 的 `/accounts/{account_id}` **之前**注册，
否则 "import" 会被当成 UUID 解析（同 accounts_bulk 的处理）。

流程：先 `/parse` 预览（不写库，让操作员确认解析结果），再 `POST /` 落库。
落库时每个号会拿到独立设备指纹、可选绑定代理与分组，并记一条导入批次（可回溯来源）。
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.config import settings
from app.models import AccountGroup, AccountImport, Proxy, TgAccount, User
from app.schemas import (
    AccountImportBatchOut,
    AccountImportParseResponse,
    AccountImportResponse,
    ImportItemPreview,
)
from app.services.account_import import (
    TDATA_HINT,
    ImportError_,
    ParsedAccount,
    import_accounts,
    parse_phone_list,
    parse_session_file,
    parse_session_strings,
    parse_tdata,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/accounts/import", tags=["accounts"])

#: 支持的导入方式（前端照着渲染引导文案，不在前端写死）
IMPORT_FORMATS: list[dict[str, Any]] = [
    {
        "kind": "phone",
        "label": "手机号清单",
        "accept": ".txt,.csv",
        "description": "每行一个号码，号码后可用逗号加备注；建档后用验证码登录拿到会话。",
    },
    {
        "kind": "session_string",
        "label": "Session 串（Telethon StringSession）",
        "accept": ".txt,.csv",
        "description": "每行一个 StringSession，也支持 `手机号,session` 或 `session,备注` 两种写法。",
    },
    {
        "kind": "session_file",
        "label": ".session 文件（Telethon / Pyrogram）",
        "accept": ".session",
        "description": "SQLite 会话文件，自动读 auth_key 与 dc_id 转成 StringSession；可一次上传多个。",
    },
    {
        "kind": "tdata",
        "label": "tdata 目录（Telegram Desktop）",
        "accept": ".zip",
        "description": "把 tdata 目录打包成 zip 上传，一个包里可以含多个账号。需要可选依赖 opentele2。",
        "hint": TDATA_HINT,
    },
]


def _preview_of(item: ParsedAccount) -> ImportItemPreview:
    """把解析结果脱敏成前端可展示的一行（不回传 session 明文）。"""
    return ImportItemPreview(
        source=item.source,
        label=item.label,
        phone_masked=item.label if item.source == "phone" else None,
        dc_id=item.dc_id,
        tg_user_id=item.tg_user_id,
        has_session=bool(item.session),
        remark=item.remark,
        error=str(item.extra.get("error") or "") or None,
    )


async def _parse_upload(file: UploadFile, kind: str) -> tuple[list[ParsedAccount], str]:
    """按类型解析一个上传文件，返回 (解析结果, 实际使用的类型)。"""
    name = (file.filename or "upload").strip()
    blob = await file.read()
    resolved = kind
    if resolved == "auto":
        lowered = name.lower()
        if lowered.endswith(".session"):
            resolved = "session_file"
        elif lowered.endswith(".zip"):
            resolved = "tdata"
        elif lowered.endswith((".txt", ".csv")):
            # 文本文件里可能混着手机号或 session 串，看首行形态
            first = blob.decode("utf-8", errors="ignore").strip().splitlines()[:1]
            resolved = "session_string" if first and "1" == first[0][:1] and len(first[0]) > 60 else "phone"
        else:
            resolved = "session_file"

    if resolved == "session_file":
        return [parse_session_file(blob, name)], resolved
    if resolved == "tdata":
        return await parse_tdata(blob, name), resolved

    text = blob.decode("utf-8", errors="ignore")
    if resolved == "session_string":
        return parse_session_strings(text), resolved
    return parse_phone_list(text), resolved


@router.get("/formats", summary="支持的导入方式（给前端渲染引导）")
async def import_formats(user: User = Depends(get_current_user)) -> dict:
    return {
        "formats": IMPORT_FORMATS,
        "max_accounts": settings.import_max_accounts,
        "tdata_available": _tdata_available(),
    }


def _tdata_available() -> bool:
    """opentele 是否可用（不可用时前端把 tdata 入口标灰并给替代路径）。"""
    try:
        import opentele.td  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


@router.post("/parse", response_model=AccountImportParseResponse, summary="解析预览（不写库）")
async def parse_import(
    kind: str = Form(default="auto", description="phone / session_string / session_file / tdata / auto"),
    text: Optional[str] = Form(default=None, description="文本清单（手机号或 session 串）"),
    files: Optional[List[UploadFile]] = File(default=None),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> AccountImportParseResponse:
    """先看清楚再导入：返回解析出来的条目（session 明文不回传）。"""
    items, used_kinds = await _collect(kind=kind, text=text, files=files)
    return AccountImportParseResponse(
        source_kind=used_kinds,
        total=len(items),
        ready=sum(1 for item in items if item.session or item.phone),
        failed=sum(1 for item in items if item.extra.get("error")),
        items=[_preview_of(item) for item in items[:200]],
        tdata_available=_tdata_available(),
    )


async def _collect(
    *, kind: str, text: Optional[str], files: Optional[List[UploadFile]]
) -> tuple[list[ParsedAccount], str]:
    """把「文本 + 若干文件」统一解析成条目列表。"""
    items: list[ParsedAccount] = []
    kinds: set[str] = set()

    if text and text.strip():
        resolved = kind
        if resolved in ("auto", "phone", "session_string"):
            if resolved == "auto":
                first = text.strip().splitlines()[0].strip()
                resolved = "session_string" if len(first) > 60 and first[:1] == "1" else "phone"
            items.extend(parse_phone_list(text) if resolved == "phone" else parse_session_strings(text))
            kinds.add(resolved)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文本清单只支持手机号清单或 Session 串；文件类请用上传",
            )

    for upload in files or []:
        if not upload.filename:
            continue
        try:
            parsed, resolved = await _parse_upload(upload, kind)
        except ImportError_ as exc:
            items.append(ParsedAccount(source=kind, label=upload.filename, extra={"error": str(exc)}))
            kinds.add(kind)
            continue
        items.extend(parsed)
        kinds.add(resolved)

    if not items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="没有可导入的内容：把清单粘到文本框，或上传 .txt / .session / tdata.zip",
        )
    if len(items) > settings.import_max_accounts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"单次最多导入 {settings.import_max_accounts} 个账号，当前 {len(items)} 个，请分批",
        )
    return items, "+".join(sorted(kinds)) if len(kinds) > 1 else (kinds.pop() if kinds else kind)


@router.post("", response_model=AccountImportResponse, summary="导入账号（建档 + 加密保存会话）")
async def run_import(
    kind: str = Form(default="auto"),
    text: Optional[str] = Form(default=None),
    files: Optional[List[UploadFile]] = File(default=None),
    proxy_id: Optional[uuid.UUID] = Form(default=None),
    group_id: Optional[uuid.UUID] = Form(default=None),
    remark: str = Form(default=""),
    start_warmup: bool = Form(default=True, description="是否从今天起计入养号阶梯"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> AccountImportResponse:
    """一次导入：解析 → 去重 → 建档 → 写批次记录。逐条结果在 results 里。"""
    if proxy_id is not None:
        proxy = await session.scalar(select(Proxy).where(Proxy.id == proxy_id))
        if proxy is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="代理不存在")
    if group_id is not None:
        group = await session.scalar(select(AccountGroup).where(AccountGroup.id == group_id))
        if group is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="分组不存在")

    items, used_kind = await _collect(kind=kind, text=text, files=files)
    outcome = await import_accounts(
        session,
        user_id=user.id,
        items=items,
        source_kind=used_kind,
        proxy_id=proxy_id,
        group_id=group_id,
        remark=remark,
        start_warmup=start_warmup,
    )
    await session.commit()
    logger.info(
        "导入接口完成 by=%s kind=%s 成功=%s 失败=%s 重复=%s",
        user.username,
        used_kind,
        outcome.succeeded,
        outcome.failed,
        outcome.duplicate,
    )
    payload = outcome.as_dict()
    return AccountImportResponse(
        ok=outcome.failed == 0,
        message=f"导入完成：成功 {outcome.succeeded}，重复 {outcome.duplicate}，失败 {outcome.failed}",
        batch_id=outcome.batch_id,
        source_kind=used_kind,
        total=outcome.total,
        succeeded=outcome.succeeded,
        failed=outcome.failed,
        duplicate=outcome.duplicate,
        results=payload["results"],
    )


@router.get("/batches", response_model=list[AccountImportBatchOut], summary="导入批次列表")
async def list_batches(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[AccountImportBatchOut]:
    rows = list(
        (
            await session.scalars(
                select(AccountImport)
                .order_by(AccountImport.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    return [AccountImportBatchOut.model_validate(row) for row in rows]


@router.get("/batches/{batch_id}", summary="导入批次详情（逐条结果）")
async def get_batch(
    batch_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    batch = await session.scalar(select(AccountImport).where(AccountImport.id == batch_id))
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="导入批次不存在")
    account_count = await session.scalar(
        select(func.count()).select_from(TgAccount).where(TgAccount.import_batch_id == batch_id)
    )
    return {
        "batch": AccountImportBatchOut.model_validate(batch),
        "accounts": int(account_count or 0),
        "results": batch.results,
    }
