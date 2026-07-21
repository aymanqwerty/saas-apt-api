import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class PatientAccount(Base, TimestampMixin):
    """A patient's login identity, scoped to a single doctor (tenant).

    Auth only — the account holder's profile and their family members live as
    `patients` rows linked via `patients.account_id`. The same phone number can
    hold an independent account under a different doctor.
    """

    __tablename__ = "patient_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="RESTRICT")
    )
    phone_number: Mapped[str] = mapped_column(String(20))
    # Optional — patients can log in with just an OTP; a password is a convenience.
    password_hash: Mapped[str | None] = mapped_column(Text)
    is_verified: Mapped[bool] = mapped_column(default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "doctor_id", "phone_number", name="uq_patient_accounts_doctor_id_phone_number"
        ),
        Index("ix_patient_accounts_doctor_id", "doctor_id"),
    )
