"""task_type 补 collect_link（按链接采集群员）

Revision ID: e6a9c1d5b802
Revises: d5f8b2c47a19
Create Date: 2026-09-29 00:45:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "e6a9c1d5b802"
down_revision: Union[str, None] = "d5f8b2c47a19"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE task_type ADD VALUE IF NOT EXISTS 'collect_link'")


def downgrade() -> None:
    # PostgreSQL 不支持从枚举中删值，保留即可
    pass
