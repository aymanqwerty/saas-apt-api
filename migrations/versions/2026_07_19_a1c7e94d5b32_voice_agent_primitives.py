"""voice agent: booking_sessions, doctor agent_api_key + website_url

Revision ID: a1c7e94d5b32
Revises: f3b8c1d29a45
Create Date: 2026-07-19 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = 'a1c7e94d5b32'
down_revision: str | None = 'f3b8c1d29a45'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('doctors', sa.Column('website_url', sa.Text(), nullable=True))
    op.add_column('doctors', sa.Column('agent_api_key', sa.String(length=64), nullable=True))
    op.create_index(
        'uq_doctors_agent_api_key',
        'doctors',
        ['agent_api_key'],
        unique=True,
        postgresql_where=sa.text('agent_api_key IS NOT NULL'),
    )

    op.create_table(
        'booking_sessions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('token', sa.String(length=48), nullable=False),
        sa.Column('doctor_id', sa.UUID(), nullable=False),
        sa.Column('clinic_id', sa.UUID(), nullable=True),
        sa.Column('slot_id', sa.UUID(), nullable=True),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('phone_number', sa.String(length=20), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('age', sa.Integer(), nullable=True),
        sa.Column(
            'gender',
            postgresql.ENUM(
                'MALE', 'FEMALE', 'OTHER', 'PREFER_NOT_TO_SAY',
                name='gender', create_type=False,
            ),
            nullable=True,
        ),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('clinic_name', sa.String(length=200), nullable=True),
        sa.Column('slot_date', sa.Date(), nullable=True),
        sa.Column('start_time', sa.Time(), nullable=True),
        sa.Column('end_time', sa.Time(), nullable=True),
        sa.Column(
            'status',
            sa.Enum('DRAFT', 'CONSUMED', 'EXPIRED', name='booking_session_status'),
            nullable=False,
        ),
        sa.Column('source', sa.String(length=30), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['doctor_id'], ['doctors.id'], name=op.f('fk_booking_sessions_doctor_id_doctors'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['clinic_id'], ['clinics.id'], name=op.f('fk_booking_sessions_clinic_id_clinics'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['slot_id'], ['slots.id'], name=op.f('fk_booking_sessions_slot_id_slots'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_booking_sessions')),
    )
    op.create_index('uq_booking_sessions_token', 'booking_sessions', ['token'], unique=True)
    op.create_index('ix_booking_sessions_doctor_id', 'booking_sessions', ['doctor_id'])


def downgrade() -> None:
    op.drop_index('ix_booking_sessions_doctor_id', table_name='booking_sessions')
    op.drop_index('uq_booking_sessions_token', table_name='booking_sessions')
    op.drop_table('booking_sessions')
    sa.Enum(name='booking_session_status').drop(op.get_bind(), checkfirst=True)

    op.drop_index('uq_doctors_agent_api_key', table_name='doctors')
    op.drop_column('doctors', 'agent_api_key')
    op.drop_column('doctors', 'website_url')
