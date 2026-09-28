"""素材库：批量私信 / 群发 / 吵群 / 拟人发言共用的文字与媒体素材。

文字素材直接存 text；媒体素材存文件（落在 `settings.materials_dir`），
任务 payload 只引用 material_id，Worker 执行时按行取文件路径发送。
"""

from __future__ import annotations

import enum
import uuid
from typing import Optional

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, uuid_pk


class MaterialKind(str, enum.Enum):
    text = "text"
    photo = "photo"
    video = "video"
    document = "document"


MATERIAL_KIND_LABELS = {
    "text": "文字",
    "photo": "图片",
    "video": "视频",
    "document": "文件",
}


class Material(Base, TimestampMixin):
    __tablename__ = "materials"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[MaterialKind] = mapped_column(
        Enum(
            MaterialKind,
            name="material_kind",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=MaterialKind.text,
        index=True,
    )
    # 文字素材的正文（媒体素材可作 caption）
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 媒体素材：相对 materials_dir 的存储文件名
    file_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    original_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mime_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
