"""campaigns: materials 素材库 + task_type 枚举扩展（批量运营 8 类任务）

Revision ID: a7b2e9d31c55
Revises: c3f1a9d24b70
Create Date: 2026-09-28 22:00:00.000000

只做加法：
1. 新表 materials（文字 / 图片 / 视频 / 文件素材，批量私信、群发、吵群共用）；
2. `task_type` 枚举新增 8 个值（bulk_pm / group_broadcast / material_send /
   join_group / leave_group / force_add_member / storm_chat / persona_chat）。

Postgres 12+ 支持在事务内 ALTER TYPE ... ADD VALUE（只是同一事务里不能立刻使用新值，
本迁移后续不再写数据，无影响）。downgrade 无法安全地从枚举里删值，只删表并留枚举。
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7b2e9d31c55"
down_revision: Union[str, None] = "c3f1a9d24b70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_TASK_TYPES = (
    "bulk_pm",
    "group_broadcast",
    "material_send",
    "join_group",
    "leave_group",
    "force_add_member",
    "storm_chat",
    "persona_chat",
)


def upgrade() -> None:
    op.create_table(
        "materials",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("text", "photo", "video", "document", name="material_kind"),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=True),
        sa.Column("original_name", sa.String(length=255), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_materials")),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_materials_created_by_users"), ondelete="SET NULL"
        ),
    )
    op.create_index(op.f("ix_materials_kind"), "materials", ["kind"], unique=False)
    for value in NEW_TASK_TYPES:
        op.execute(f"ALTER TYPE task_type ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # PostgreSQL 不支持从枚举中删值：task_type 的新值保留（只影响枚举，不影响数据）
    op.drop_index(op.f("ix_materials_kind"), table_name="materials")
    op.drop_table("materials")
