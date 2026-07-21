"""initial baseline

Revision ID: ff68980e3b5e
Revises: 
Create Date: 2026-07-16 13:33:46.003645

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'ff68980e3b5e'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
