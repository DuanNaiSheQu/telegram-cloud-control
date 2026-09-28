"""group intel: 群档案 / 群成员 / 入退群事件流（无感采集的数据底座）

Revision ID: d5f8b2c47a19
Revises: c4e7a1b93f28
Create Date: 2026-09-29 00:20:00.000000

三张新表，只做加法：
- `group_profiles`：群档案（一号一群一行，含成员数、简介、邀请链接、采集进度）
- `group_members`：成员快照（唯一键 群+用户，反复采集只更新）
- `group_events`：入/退群流水（含「被谁拉进来」与去重键）

同时给 `task_type` 枚举加 collect_group / collect_members 两个只读采集任务。
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d5f8b2c47a19"
down_revision: Union[str, None] = "c4e7a1b93f28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_TASK_TYPES = ("collect_group", "collect_members")


def upgrade() -> None:
    op.create_table(
        "group_profiles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=True),
        sa.Column("dialog_id", sa.UUID(), nullable=True),
        sa.Column("tg_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="group"),
        sa.Column("member_count", sa.Integer(), nullable=True),
        sa.Column("about", sa.Text(), nullable=False, server_default=""),
        sa.Column("invite_link", sa.String(length=255), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_restricted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("creator_tg_id", sa.BigInteger(), nullable=True),
        sa.Column("tg_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("member_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("member_sampled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(length=24), nullable=False, server_default="profile_sync"),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_group_profiles")),
        sa.ForeignKeyConstraint(
            ["account_id"], ["tg_accounts.id"], name=op.f("fk_group_profiles_account_id_tg_accounts"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["dialog_id"], ["dialogs.id"], name=op.f("fk_group_profiles_dialog_id_dialogs"), ondelete="SET NULL"
        ),
        sa.UniqueConstraint("account_id", "tg_chat_id", name="uq_group_profiles_account_chat"),
    )
    op.create_index(op.f("ix_group_profiles_account_id"), "group_profiles", ["account_id"])
    op.create_index(op.f("ix_group_profiles_tg_chat_id"), "group_profiles", ["tg_chat_id"])
    op.create_index("ix_group_profiles_member_count", "group_profiles", ["member_count"])

    op.create_table(
        "group_members",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("group_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=True),
        sa.Column("tg_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("tg_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("display_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("is_bot", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_premium", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="member"),
        sa.Column("source", sa.String(length=24), nullable=False, server_default="participant_sync"),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_group_members")),
        sa.ForeignKeyConstraint(
            ["group_id"], ["group_profiles.id"], name=op.f("fk_group_members_group_id_group_profiles"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["tg_accounts.id"], name=op.f("fk_group_members_account_id_tg_accounts"), ondelete="SET NULL"
        ),
        sa.UniqueConstraint("tg_chat_id", "tg_user_id", name="uq_group_members_chat_user"),
    )
    op.create_index(op.f("ix_group_members_group_id"), "group_members", ["group_id"])
    op.create_index(op.f("ix_group_members_tg_chat_id"), "group_members", ["tg_chat_id"])
    op.create_index(op.f("ix_group_members_tg_user_id"), "group_members", ["tg_user_id"])
    op.create_index("ix_group_members_chat_status", "group_members", ["tg_chat_id", "status"])

    op.create_table(
        "group_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=True),
        sa.Column("tg_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("tg_user_id", sa.BigInteger(), nullable=True),
        sa.Column("event_type", sa.String(length=16), nullable=False, server_default="join"),
        sa.Column("actor_tg_id", sa.BigInteger(), nullable=True),
        sa.Column("user_display", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("is_bot", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("source", sa.String(length=24), nullable=False, server_default="join_event"),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_group_events")),
        sa.ForeignKeyConstraint(
            ["account_id"], ["tg_accounts.id"], name=op.f("fk_group_events_account_id_tg_accounts"), ondelete="CASCADE"
        ),
        sa.UniqueConstraint("tg_chat_id", "tg_user_id", "event_type", "occurred_at", name="uq_group_events_dedupe"),
    )
    op.create_index(op.f("ix_group_events_tg_chat_id"), "group_events", ["tg_chat_id"])
    op.create_index(op.f("ix_group_events_tg_user_id"), "group_events", ["tg_user_id"])
    op.create_index(op.f("ix_group_events_event_type"), "group_events", ["event_type"])
    op.create_index(op.f("ix_group_events_occurred_at"), "group_events", ["occurred_at"])
    op.create_index("ix_group_events_chat_time", "group_events", ["tg_chat_id", "occurred_at"])

    for value in NEW_TASK_TYPES:
        op.execute(f"ALTER TYPE task_type ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    op.drop_table("group_events")
    op.drop_table("group_members")
    op.drop_table("group_profiles")
