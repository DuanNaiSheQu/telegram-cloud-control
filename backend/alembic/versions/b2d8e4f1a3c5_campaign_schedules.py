"""群发定时计划：到点自动把群发 / 私信批次排进任务队列

Revision ID: b2d8e4f1a3c5
Revises: a1c7f3e9b2d4
Create Date: 2026-09-29 23:05:00.000000

- `campaign_schedules`：一条计划 = 一份提交参数 + 间隔 + 时间窗，
  调度器到点按它展开「一号一任务」，页面下方实时显示下次执行与已跑次数。
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b2d8e4f1a3c5"
down_revision: Union[str, None] = "a1c7f3e9b2d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "campaign_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("interval_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("send_window", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("run_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_campaign_schedules")),
    )
    op.create_index(op.f("ix_campaign_schedules_enabled"), "campaign_schedules", ["enabled"], unique=False)
    op.create_index(
        op.f("ix_campaign_schedules_next_run_at"), "campaign_schedules", ["next_run_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_campaign_schedules_next_run_at"), table_name="campaign_schedules")
    op.drop_index(op.f("ix_campaign_schedules_enabled"), table_name="campaign_schedules")
    op.drop_table("campaign_schedules")
