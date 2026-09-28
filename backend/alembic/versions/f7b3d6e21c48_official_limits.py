"""官方机制：账号级官方客户端身份 + 服务端下发限制参数快照

Revision ID: f7b3d6e21c48
Revises: e6a9c1d5b802
Create Date: 2026-09-29 01:10:00.000000

- `client_kind`：对齐的官方客户端平台（android / ios / tdesktop）
- `official_limits`：help.GetAppConfig 里 flood/上限类参数快照，节流时只收紧不放松
- `official_synced_at` / `warmup_active_at`：同步时间与最近一次养号活动时间
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f7b3d6e21c48"
down_revision: Union[str, None] = "e6a9c1d5b802"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tg_accounts", sa.Column("client_kind", sa.String(length=16), nullable=False, server_default=""))
    op.add_column(
        "tg_accounts",
        sa.Column("official_limits", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
    )
    op.add_column("tg_accounts", sa.Column("official_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tg_accounts", sa.Column("warmup_active_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_tg_accounts_client_kind"), "tg_accounts", ["client_kind"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tg_accounts_client_kind"), table_name="tg_accounts")
    for column in ("warmup_active_at", "official_synced_at", "official_limits", "client_kind"):
        op.drop_column("tg_accounts", column)
