"""task_type 补 search_groups（按关键词找群）

Revision ID: c8e2a37d1f60
Revises: b7d1f26c9e05
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "c8e2a37d1f60"
down_revision: Union[str, None] = "b7d1f26c9e05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE task_type ADD VALUE IF NOT EXISTS 'search_groups'")


def downgrade() -> None:
    pass
