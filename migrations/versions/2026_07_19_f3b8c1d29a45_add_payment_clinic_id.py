"""add clinic_id to payments (filterable by clinic)

Revision ID: f3b8c1d29a45
Revises: e7a2c9d4b016
Create Date: 2026-07-19 09:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'f3b8c1d29a45'
down_revision: str | None = 'e7a2c9d4b016'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('payments', sa.Column('clinic_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f('fk_payments_clinic_id_clinics'),
        'payments', 'clinics', ['clinic_id'], ['id'], ondelete='SET NULL',
    )
    op.create_index('ix_payments_clinic_id', 'payments', ['clinic_id'])


def downgrade() -> None:
    op.drop_index('ix_payments_clinic_id', table_name='payments')
    op.drop_constraint(op.f('fk_payments_clinic_id_clinics'), 'payments', type_='foreignkey')
    op.drop_column('payments', 'clinic_id')
