"""create patient_accounts, otp_challenges, patient account fields

Revision ID: e7a2c9d4b016
Revises: c4d1a9b7e210
Create Date: 2026-07-18 15:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'e7a2c9d4b016'
down_revision: str | None = 'c4d1a9b7e210'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_RELATIONSHIP = sa.Enum(
    'SELF', 'SPOUSE', 'FATHER', 'MOTHER', 'SON', 'DAUGHTER',
    'BROTHER', 'SISTER', 'GUARDIAN', 'OTHER',
    name='patient_relationship',
)


def upgrade() -> None:
    op.create_table(
        'patient_accounts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('doctor_id', sa.UUID(), nullable=False),
        sa.Column('phone_number', sa.String(length=20), nullable=False),
        sa.Column('password_hash', sa.Text(), nullable=True),
        sa.Column('is_verified', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['doctor_id'], ['doctors.id'], name=op.f('fk_patient_accounts_doctor_id_doctors'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_patient_accounts')),
        sa.UniqueConstraint('doctor_id', 'phone_number', name='uq_patient_accounts_doctor_id_phone_number'),
    )
    op.create_index('ix_patient_accounts_doctor_id', 'patient_accounts', ['doctor_id'])

    op.create_table(
        'otp_challenges',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('doctor_id', sa.UUID(), nullable=False),
        sa.Column('phone_number', sa.String(length=20), nullable=False),
        sa.Column('code_hash', sa.Text(), nullable=False),
        sa.Column('purpose', sa.Enum('AUTH', name='otp_purpose'), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['doctor_id'], ['doctors.id'], name=op.f('fk_otp_challenges_doctor_id_doctors'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_otp_challenges')),
    )
    op.create_index('ix_otp_challenges_doctor_id_phone_number', 'otp_challenges', ['doctor_id', 'phone_number'])

    # Patient account linkage + richer profile fields.
    _RELATIONSHIP.create(op.get_bind(), checkfirst=True)
    op.add_column('patients', sa.Column('account_id', sa.UUID(), nullable=True))
    op.add_column('patients', sa.Column('relationship', _RELATIONSHIP, nullable=True))
    op.add_column('patients', sa.Column('date_of_birth', sa.Date(), nullable=True))
    op.create_foreign_key(
        op.f('fk_patients_account_id_patient_accounts'),
        'patients', 'patient_accounts', ['account_id'], ['id'], ondelete='SET NULL',
    )
    op.create_index('ix_patients_account_id', 'patients', ['account_id'])

    # Replace the strict one-patient-per-phone rule with a partial unique index
    # that only constrains "primary" patients (guests + account holders), so
    # family members can share the account holder's phone number.
    op.drop_constraint('uq_patients_doctor_id_phone_number', 'patients', type_='unique')
    op.create_index(
        'uq_patients_doctor_primary_phone',
        'patients',
        ['doctor_id', 'phone_number'],
        unique=True,
        postgresql_where=sa.text("relationship IS NULL OR relationship = 'SELF'"),
    )


def downgrade() -> None:
    op.drop_index('uq_patients_doctor_primary_phone', table_name='patients')
    op.create_unique_constraint(
        'uq_patients_doctor_id_phone_number', 'patients', ['doctor_id', 'phone_number']
    )
    op.drop_index('ix_patients_account_id', table_name='patients')
    op.drop_constraint(op.f('fk_patients_account_id_patient_accounts'), 'patients', type_='foreignkey')
    op.drop_column('patients', 'date_of_birth')
    op.drop_column('patients', 'relationship')
    op.drop_column('patients', 'account_id')

    op.drop_index('ix_otp_challenges_doctor_id_phone_number', table_name='otp_challenges')
    op.drop_table('otp_challenges')
    op.drop_index('ix_patient_accounts_doctor_id', table_name='patient_accounts')
    op.drop_table('patient_accounts')

    _RELATIONSHIP.drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='otp_purpose').drop(op.get_bind(), checkfirst=True)
