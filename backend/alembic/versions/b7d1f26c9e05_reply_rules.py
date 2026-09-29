"""reply_rules：账号自动回复规则

Revision ID: b7d1f26c9e05
Revises: a6c0e15b8d94
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7d1f26c9e05"
down_revision: Union[str, None] = "a6c0e15b8d94"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reply_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("keywords", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("reply_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("match_mode", sa.String(length=16), nullable=False, server_default="contains"),
        sa.Column("scope", sa.String(length=16), nullable=False, server_default="private"),
        sa.Column("account_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("cooldown_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_reply_rules_enabled", "reply_rules", ["enabled"])


def downgrade() -> None:
    op.drop_index("ix_reply_rules_enabled", table_name="reply_rules")
    op.drop_table("reply_rules")
