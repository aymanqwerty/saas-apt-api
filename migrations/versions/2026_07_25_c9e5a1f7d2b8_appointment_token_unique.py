"""unique token_number per clinic-day

Revision ID: c9e5a1f7d2b8
Revises: b8d3f1e64c27
Create Date: 2026-07-25 12:00:00.000000

"""
from collections.abc import Sequence

from alembic import op


revision: str = 'c9e5a1f7d2b8'
down_revision: str | None = 'b8d3f1e64c27'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        'uq_appointments_clinic_date_token',
        'appointments',
        ['clinic_id', 'appointment_date', 'token_number'],
    )


def downgrade() -> None:
    op.drop_constraint(
        'uq_appointments_clinic_date_token', 'appointments', type_='unique'
    )
