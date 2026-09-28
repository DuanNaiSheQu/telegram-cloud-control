"""account matrix: 账号矩阵字段（导入来源 / 设备指纹 / 健康分 / 节流养号）+ account_imports 批次表

Revision ID: b2d4f81a6c93
Revises: a7b2e9d31c55
Create Date: 2026-09-28 23:30:00.000000

只做加法：
1. `tg_accounts` 增列：导入来源与批次、设备指纹（device_model/system_version/app_version/lang_code/lang_pack）、
   验活结果（health_score/health_checked_at/health_detail/risk_flags）、节流养号
   （daily_message_limit/min_action_seconds/warmup_started_at/flood_until/flood_strikes）；
2. 新表 `account_imports`：记录每次批量导入的来源、总数与逐条结果。

默认值都让老数据保持原语义：health_score=100、import_source=manual、节流 0 表示走默认阶梯。
`alembic downgrade -1` 会删表并去掉这些列，不影响其它字段。
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b2d4f81a6c93"
down_revision: Union[str, None] = "a7b2e9d31c55"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ACCOUNT_COLUMNS = (
    sa.Column("import_source", sa.String(length=24), nullable=False, server_default="manual"),
    sa.Column("import_batch_id", sa.UUID(), nullable=True),
    sa.Column("device_model", sa.String(length=64), nullable=False, server_default=""),
    sa.Column("system_version", sa.String(length=32), nullable=False, server_default=""),
    sa.Column("app_version", sa.String(length=32), nullable=False, server_default=""),
    sa.Column("lang_code", sa.String(length=8), nullable=False, server_default="zh"),
    sa.Column("lang_pack", sa.String(length=8), nullable=False, server_default=""),
    sa.Column("health_score", sa.Integer(), nullable=False, server_default="100"),
    sa.Column("health_checked_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("health_detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
    sa.Column("risk_flags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
    sa.Column("daily_message_limit", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("min_action_seconds", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("warmup_started_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("flood_until", sa.DateTime(timezone=True), nullable=True),
    sa.Column("flood_strikes", sa.Integer(), nullable=False, server_default="0"),
)


def upgrade() -> None:
    for column in ACCOUNT_COLUMNS:
        op.add_column("tg_accounts", column)
    op.create_index(op.f("ix_tg_accounts_import_source"), "tg_accounts", ["import_source"], unique=False)
    op.create_index(op.f("ix_tg_accounts_import_batch_id"), "tg_accounts", ["import_batch_id"], unique=False)

    op.create_table(
        "account_imports",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("source_kind", sa.String(length=24), nullable=False, server_default="mixed"),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("succeeded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("proxy_id", sa.UUID(), nullable=True),
        sa.Column("group_id", sa.UUID(), nullable=True),
        sa.Column("results", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("remark", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_account_imports")),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_account_imports_created_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["proxy_id"], ["proxies.id"], name=op.f("fk_account_imports_proxy_id_proxies"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["account_groups.id"],
            name=op.f("fk_account_imports_group_id_account_groups"),
            ondelete="SET NULL",
        ),
    )


def downgrade() -> None:
    op.drop_table("account_imports")
    op.drop_index(op.f("ix_tg_accounts_import_batch_id"), table_name="tg_accounts")
    op.drop_index(op.f("ix_tg_accounts_import_source"), table_name="tg_accounts")
    for column in reversed(ACCOUNT_COLUMNS):
        op.drop_column("tg_accounts", column.name)
