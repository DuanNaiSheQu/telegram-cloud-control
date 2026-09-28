"""素材库：文字素材直接落库，媒体素材落盘（settings.materials_dir）+ 库里存引用。

文件读写都收敛在 settings.materials_dir 下：存储名由服务端生成（uuid8 后缀），
客户端给的文件名只作 original_name 展示，杜绝路径穿越。
"""

from __future__ import annotations

import logging
import pathlib
import uuid
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.api.routers import build_order_by
from app.config import settings
from app.core.audit import write_audit
from app.models import MATERIAL_KIND_LABELS, Material, MaterialKind, User
from app.schemas import MaterialCreate, MaterialListResponse, MaterialOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/materials", tags=["materials"])

#: 媒体素材大小上限（字节）
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

#: 允许的媒体扩展名 → kind
EXT_KIND = {
    ".jpg": MaterialKind.photo, ".jpeg": MaterialKind.photo, ".png": MaterialKind.photo,
    ".webp": MaterialKind.photo, ".gif": MaterialKind.photo, ".bmp": MaterialKind.photo,
    ".mp4": MaterialKind.video, ".mov": MaterialKind.video, ".avi": MaterialKind.video,
    ".mkv": MaterialKind.video, ".webm": MaterialKind.video,
}
#: 其余一律按文件（document）处理


def _materials_dir() -> pathlib.Path:
    path = pathlib.Path(settings.materials_dir)
    if not path.is_absolute():
        path = pathlib.Path.cwd() / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _material_out(row: Material) -> MaterialOut:
    out = MaterialOut.model_validate(row)
    out.kind_label = MATERIAL_KIND_LABELS.get(row.kind.value, row.kind.value)
    return out


@router.get("", response_model=MaterialListResponse, summary="素材列表")
async def list_materials(
    kind: Optional[MaterialKind] = Query(default=None),
    q: Optional[str] = Query(default=None, description="按名称模糊搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: Optional[str] = Query(default=None, description="created_at | name"),
    order: Optional[str] = Query(default=None, description="asc | desc"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> MaterialListResponse:
    conditions = []
    if kind is not None:
        conditions.append(Material.kind == kind)
    if q:
        conditions.append(Material.name.ilike(f"%{q.strip()}%"))
    total = await session.scalar(select(func.count()).select_from(Material).where(*conditions))
    order_by = build_order_by(
        sort=sort,
        order=order,
        mapping={"created_at": Material.created_at, "name": Material.name},
        default_field="created_at",
        default_order="desc",
        tiebreaker=Material.id,
    )
    rows = list(
        (
            await session.scalars(
                select(Material).where(*conditions).order_by(*order_by).offset((page - 1) * page_size).limit(page_size)
            )
        ).all()
    )
    return MaterialListResponse(
        items=[_material_out(row) for row in rows],
        total=int(total or 0),
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=MaterialOut, summary="新建文字素材")
async def create_text_material(
    payload: MaterialCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> MaterialOut:
    if payload.kind != MaterialKind.text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="媒体素材请用 /api/materials/upload 上传；该接口只收文字素材",
        )
    row = Material(
        name=payload.name.strip(),
        kind=MaterialKind.text,
        text=(payload.text or "").strip(),
        created_by=user.id,
    )
    session.add(row)
    await write_audit(
        session,
        action="material.create",
        user_id=user.id,
        target_type="material",
        target_id=str(row.id),
        detail={"name": row.name, "kind": row.kind.value},
    )
    await session.commit()
    await session.refresh(row)
    logger.info("新建文字素材 material_id=%s by=%s", row.id, user.username)
    return _material_out(row)


@router.post("/upload", response_model=MaterialOut, summary="上传媒体素材（图片 / 视频 / 文件）")
async def upload_material(
    name: str = Query(min_length=1, max_length=128, description="素材名"),
    file: UploadFile = File(description="媒体文件，最大 20MB"),
    caption: Optional[str] = Query(default=None, max_length=4000, description="随媒体一起发送的文字"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> MaterialOut:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="上传内容为空")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件超过 20MB 上限")

    original = (file.filename or "file").strip() or "file"
    suffix = pathlib.Path(original).suffix.lower()
    kind = EXT_KIND.get(suffix, MaterialKind.document)
    stored = f"{uuid.uuid4().hex}{suffix or '.bin'}"
    target = _materials_dir() / stored
    target.write_bytes(content)

    row = Material(
        name=name.strip(),
        kind=kind,
        text=(caption or "").strip(),
        file_name=stored,
        original_name=original,
        size_bytes=len(content),
        mime_type=file.content_type or None,
        created_by=user.id,
    )
    session.add(row)
    await write_audit(
        session,
        action="material.upload",
        user_id=user.id,
        target_type="material",
        target_id=str(row.id),
        detail={"name": row.name, "kind": kind.value, "bytes": len(content), "original_name": original},
    )
    await session.commit()
    await session.refresh(row)
    logger.info("上传素材 material_id=%s kind=%s bytes=%s by=%s", row.id, kind.value, len(content), user.username)
    return _material_out(row)


@router.get("/{material_id}", summary="素材详情 / 下载媒体文件")
async def get_material(
    material_id: uuid.UUID,
    download: bool = Query(default=False, description="媒体素材传 true 直接下载文件"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    row = await session.get(Material, material_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="素材不存在")
    if not download or row.kind == MaterialKind.text:
        return _material_out(row)
    if not row.file_name:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该素材没有媒体文件")
    path = _materials_dir() / row.file_name
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="素材文件已丢失，请重新上传")
    return FileResponse(
        path,
        media_type=row.mime_type or "application/octet-stream",
        filename=row.original_name or row.file_name,
    )


@router.delete("/{material_id}", summary="删除素材")
async def delete_material(
    material_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    row = await session.get(Material, material_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="素材不存在")
    file_name = row.file_name
    await session.delete(row)
    await write_audit(
        session,
        action="material.delete",
        user_id=user.id,
        target_type="material",
        target_id=str(material_id),
        detail={"name": row.name, "kind": row.kind.value},
    )
    await session.commit()
    if file_name:
        path = _materials_dir() / file_name
        try:
            path.unlink(missing_ok=True)
        except OSError:  # noqa: BLE001 - 文件删不掉不影响行删除
            logger.warning("素材文件删除失败 material_id=%s file=%s", material_id, file_name)
    logger.info("删除素材 material_id=%s by=%s", material_id, user.username)
    return {"ok": True, "message": "已删除"}
