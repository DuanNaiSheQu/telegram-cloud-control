"""task_type 补 screen_groups（筛群检测）

Revision ID: f5b9d04a7c83
Revises: e4a8c93f6b72
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "f5b9d04a7c83"
down_revision: Union[str, None] = "e4a8c93f6b72"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE task_type ADD VALUE IF NOT EXISTS 'screen_groups'")


def downgrade() -> None:
    pass
