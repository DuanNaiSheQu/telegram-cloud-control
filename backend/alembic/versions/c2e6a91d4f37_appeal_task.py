"""task_type 补 appeal_spam（模拟真人向 SpamBot 申诉）

Revision ID: c2e6a91d4f37
Revises: b1d5f80c7e42
Create Date: 2026-03-30 12:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "c2e6a91d4f37"
down_revision: Union[str, None] = "b1d5f80c7e42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE task_type ADD VALUE IF NOT EXISTS 'appeal_spam'")


def downgrade() -> None:
    pass
