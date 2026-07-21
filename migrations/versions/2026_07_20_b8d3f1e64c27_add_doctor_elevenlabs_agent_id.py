"""add doctors.elevenlabs_agent_id

Revision ID: b8d3f1e64c27
Revises: a1c7e94d5b32
Create Date: 2026-07-20 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'b8d3f1e64c27'
down_revision: str | None = 'a1c7e94d5b32'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('doctors', sa.Column('elevenlabs_agent_id', sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column('doctors', 'elevenlabs_agent_id')
