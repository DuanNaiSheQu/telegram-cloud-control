"""账号状态加「临时受限」：限流不是封号

Revision ID: c3e9f5a2b4d6
Revises: b2d8e4f1a3c5
Create Date: 2026-09-29 23:20:00.000000

- 新增 `limited` 状态：FloodWait 这类**临时**限制标成它，而不是一棍子打成 `frozen`；
  `limited` 不粘性——下一次成功操作（连接 / 检测 / 发送）就会自己回到 `healthy`。
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "c3e9f5a2b4d6"
down_revision: Union[str, None] = "b2d8e4f1a3c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL 的枚举加值不能在事务里回滚，得走 autocommit 块
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE account_status ADD VALUE IF NOT EXISTS 'limited'")


def downgrade() -> None:
    # PostgreSQL 不支持删除枚举值；回滚时保留该值（不影响老代码按老值判断）
    pass
