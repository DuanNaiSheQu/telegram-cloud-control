"""console completeness: metrics_samples + notifications

Revision ID: c3f1a9d24b70
Revises: 7ff4628ae5cf
Create Date: 2026-09-28 21:30:00.000000

只做加法：两张新表（趋势采样 + 站内通知），不改任何已有列语义。
`alembic downgrade -1` 会把这两张表删掉，现有数据不受影响。
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3f1a9d24b70"
down_revision: Union[str, None] = "7ff4628ae5cf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- 趋势采样：一小时一行（bucket 为主键），采样协程 UPSERT ----
    op.create_table(
        "metrics_samples",
        sa.Column("bucket", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_accounts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("online_accounts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("abnormal_accounts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("tasks_succeeded", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("tasks_failed", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("sampled_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("bucket", name=op.f("pk_metrics_samples")),
    )

    # ---- 站内通知：失败任务 / Worker 丢失 / 账号异常 / 备份失败 的聚合结果 ----
    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("link", sa.String(length=255), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=True),
        sa.Column("bot_id", sa.UUID(), nullable=True),
        sa.Column("task_id", sa.UUID(), nullable=True),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("dedupe_key", sa.String(length=200), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"], ["tg_accounts.id"],
            name=op.f("fk_notifications_account_id_tg_accounts"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["bot_id"], ["bots.id"],
            name=op.f("fk_notifications_bot_id_bots"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"],
            name=op.f("fk_notifications_task_id_tasks"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["read_by"], ["users.id"],
            name=op.f("fk_notifications_read_by_users"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        sa.UniqueConstraint("dedupe_key", name=op.f("uq_notifications_dedupe_key")),
    )
    op.create_index(op.f("ix_notifications_account_id"), "notifications", ["account_id"], unique=False)
    op.create_index(op.f("ix_notifications_bot_id"), "notifications", ["bot_id"], unique=False)
    op.create_index(op.f("ix_notifications_is_read"), "notifications", ["is_read"], unique=False)
    op.create_index(op.f("ix_notifications_kind"), "notifications", ["kind"], unique=False)
    op.create_index(op.f("ix_notifications_task_id"), "notifications", ["task_id"], unique=False)
    op.create_index("ix_notifications_read_created", "notifications", ["is_read", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_notifications_read_created", table_name="notifications")
    op.drop_index(op.f("ix_notifications_task_id"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_kind"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_is_read"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_bot_id"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_account_id"), table_name="notifications")
    op.drop_table("notifications")
    op.drop_table("metrics_samples")
