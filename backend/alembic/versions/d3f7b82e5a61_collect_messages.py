"""task_type 补 collect_messages（采集群内对话）

Revision ID: d3f7b82e5a61
Revises: c2e6a91d4f37
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "d3f7b82e5a61"
down_revision: Union[str, None] = "c2e6a91d4f37"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE task_type ADD VALUE IF NOT EXISTS 'collect_messages'")


def downgrade() -> None:
    pass
