"""account phone_hash：手机号确定性哈希，导入/建档共用的去重键

Revision ID: c4e7a1b93f28
Revises: b2d4f81a6c93
Create Date: 2026-09-28 23:55:00.000000

背景：`phone_enc` 是 Fernet 密文（带随机 IV），同一号码每次加密结果不同，
拿密文做等值查询永远查不到，导致批量导入重复号码识别不出来。
这里加一列确定性哈希（sha256 前 16 位），并把索引加上；老数据由后台回填补齐即可。
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4e7a1b93f28"
down_revision: Union[str, None] = "b2d4f81a6c93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tg_accounts", sa.Column("phone_hash", sa.String(length=64), nullable=True))
    op.create_index(op.f("ix_tg_accounts_phone_hash"), "tg_accounts", ["phone_hash"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tg_accounts_phone_hash"), table_name="tg_accounts")
    op.drop_column("tg_accounts", "phone_hash")
