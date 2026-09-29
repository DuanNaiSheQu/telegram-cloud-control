"""账号自动归档字段

加 archived_at / archive_reason：检测确认用不了的号自动归档，默认不显示在主列表，
但保留数据并记录原因，便于事后管理。

Revision ID: a1c7f3e9b2d4
Revises: 49dea35d6455
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1c7f3e9b2d4"
down_revision: Union[str, None] = "49dea35d6455"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tg_accounts", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "tg_accounts",
        sa.Column("archive_reason", sa.String(length=255), nullable=False, server_default=""),
    )
    op.create_index("ix_tg_accounts_archived_at", "tg_accounts", ["archived_at"])


def downgrade() -> None:
    op.drop_index("ix_tg_accounts_archived_at", table_name="tg_accounts")
    op.drop_column("tg_accounts", "archive_reason")
    op.drop_column("tg_accounts", "archived_at")
