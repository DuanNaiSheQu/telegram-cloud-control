"""task_type 补 sync_official / warmup_activity

Revision ID: a8c4e7f31b95
Revises: f7b3d6e21c48
Create Date: 2026-09-29 01:25:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "a8c4e7f31b95"
down_revision: Union[str, None] = "f7b3d6e21c48"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_TYPES = ("sync_official", "warmup_activity")


def upgrade() -> None:
    for value in NEW_TYPES:
        op.execute(f"ALTER TYPE task_type ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    pass
