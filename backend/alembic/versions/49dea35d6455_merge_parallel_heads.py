"""merge parallel heads

Revision ID: 49dea35d6455
Revises: c8e2a37d1f60, f5b9d14a7c83
Create Date: 2026-09-29 20:54:51.545714

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '49dea35d6455'
down_revision: Union[str, None] = ('c8e2a37d1f60', 'f5b9d14a7c83')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
