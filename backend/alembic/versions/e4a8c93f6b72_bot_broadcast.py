"""task_type 补 bot_broadcast（Bot 群发/转发）

Revision ID: e4a8c93f6b72
Revises: d3f7b82e5a61
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "e4a8c93f6b72"
down_revision: Union[str, None] = "d3f7b82e5a61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE task_type ADD VALUE IF NOT EXISTS 'bot_broadcast'")


def downgrade() -> None:
    pass
