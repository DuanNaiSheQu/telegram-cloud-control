"""tg_accounts 增加 api_id：记录该号通过哪套 API 凭据登录

Revision ID: b1d5f80c7e42
Revises: a8c4e7f31b95
Create Date: 2026-03-30 10:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b1d5f80c7e42"
down_revision: Union[str, None] = "a8c4e7f31b95"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tg_accounts", sa.Column("api_id", sa.BigInteger(), nullable=True))
    op.create_index(op.f("ix_tg_accounts_api_id"), "tg_accounts", ["api_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tg_accounts_api_id"), table_name="tg_accounts")
    op.drop_column("tg_accounts", "api_id")
