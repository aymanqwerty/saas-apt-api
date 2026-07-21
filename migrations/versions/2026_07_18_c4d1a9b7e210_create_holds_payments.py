"""create appointment_holds and payments, add payment_required

Revision ID: c4d1a9b7e210
Revises: dc0c802e469e
Create Date: 2026-07-18 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'c4d1a9b7e210'
down_revision: str | None = 'dc0c802e469e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'doctor_settings',
        sa.Column(
            'payment_required',
            sa.Boolean(),
            server_default=sa.text('false'),
            nullable=False,
        ),
    )

    op.create_table(
        'appointment_holds',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('doctor_id', sa.UUID(), nullable=False),
        sa.Column('clinic_id', sa.UUID(), nullable=False),
        sa.Column('slot_id', sa.UUID(), nullable=False),
        sa.Column('patient_id', sa.UUID(), nullable=False),
        sa.Column('visit_reason', sa.Text(), nullable=True),
        sa.Column(
            'status',
            sa.Enum('HELD', 'CONFIRMED', 'EXPIRED', 'CANCELLED', name='hold_status'),
            nullable=False,
        ),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['doctor_id'], ['doctors.id'], name=op.f('fk_appointment_holds_doctor_id_doctors'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['clinic_id'], ['clinics.id'], name=op.f('fk_appointment_holds_clinic_id_clinics'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['slot_id'], ['slots.id'], name=op.f('fk_appointment_holds_slot_id_slots'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], name=op.f('fk_appointment_holds_patient_id_patients'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_appointment_holds')),
    )
    op.create_index('ix_appointment_holds_slot_id', 'appointment_holds', ['slot_id'])
    op.create_index('ix_appointment_holds_status_expires_at', 'appointment_holds', ['status', 'expires_at'])

    op.create_table(
        'payments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('doctor_id', sa.UUID(), nullable=False),
        sa.Column('hold_id', sa.UUID(), nullable=True),
        sa.Column('appointment_id', sa.UUID(), nullable=True),
        sa.Column('patient_id', sa.UUID(), nullable=True),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column(
            'status',
            sa.Enum('PENDING', 'PAID', 'FAILED', 'REFUNDED', name='payment_status'),
            nullable=False,
        ),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('provider_order_id', sa.String(length=255), nullable=True),
        sa.Column('provider_payment_id', sa.String(length=255), nullable=True),
        sa.Column('provider_signature', sa.Text(), nullable=True),
        sa.Column('patient_name', sa.String(length=150), nullable=False),
        sa.Column('clinic_name', sa.String(length=200), nullable=False),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('refund_id', sa.String(length=255), nullable=True),
        sa.Column('refunded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['doctor_id'], ['doctors.id'], name=op.f('fk_payments_doctor_id_doctors'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['hold_id'], ['appointment_holds.id'], name=op.f('fk_payments_hold_id_appointment_holds'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['appointment_id'], ['appointments.id'], name=op.f('fk_payments_appointment_id_appointments'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], name=op.f('fk_payments_patient_id_patients'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_payments')),
    )
    op.create_index('ix_payments_doctor_id', 'payments', ['doctor_id'])
    op.create_index('ix_payments_doctor_id_created_at', 'payments', ['doctor_id', 'created_at'])
    op.create_index('ix_payments_provider_order_id', 'payments', ['provider_order_id'])


def downgrade() -> None:
    op.drop_index('ix_payments_provider_order_id', table_name='payments')
    op.drop_index('ix_payments_doctor_id_created_at', table_name='payments')
    op.drop_index('ix_payments_doctor_id', table_name='payments')
    op.drop_table('payments')
    op.drop_index('ix_appointment_holds_status_expires_at', table_name='appointment_holds')
    op.drop_index('ix_appointment_holds_slot_id', table_name='appointment_holds')
    op.drop_table('appointment_holds')
    op.drop_column('doctor_settings', 'payment_required')
    sa.Enum(name='payment_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='hold_status').drop(op.get_bind(), checkfirst=True)
