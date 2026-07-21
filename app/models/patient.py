import enum
import uuid
from datetime import date

from sqlalchemy import Date as SADate
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class Gender(enum.StrEnum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"
    PREFER_NOT_TO_SAY = "PREFER_NOT_TO_SAY"


class PatientRelationship(enum.StrEnum):
    """How a patient relates to the account that owns it.

    SELF is the account holder's own record; the rest are family members.
    Guest (non-account) patients have no relationship (NULL).
    """

    SELF = "SELF"
    SPOUSE = "SPOUSE"
    FATHER = "FATHER"
    MOTHER = "MOTHER"
    SON = "SON"
    DAUGHTER = "DAUGHTER"
    BROTHER = "BROTHER"
    SISTER = "SISTER"
    GUARDIAN = "GUARDIAN"
    OTHER = "OTHER"


class Patient(Base, TimestampMixin):
    __tablename__ = "patients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="RESTRICT")
    )
    # The patient account this record belongs to. NULL for guest bookings.
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patient_accounts.id", ondelete="SET NULL")
    )
    relationship: Mapped[PatientRelationship | None] = mapped_column(
        SAEnum(PatientRelationship, name="patient_relationship")
    )
    patient_code: Mapped[str] = mapped_column(String(20))
    full_name: Mapped[str] = mapped_column(String(150))
    phone_number: Mapped[str] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(255))
    age: Mapped[int | None] = mapped_column(Integer)
    date_of_birth: Mapped[date | None] = mapped_column(SADate)
    gender: Mapped[Gender | None] = mapped_column(SAEnum(Gender, name="gender"))
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("doctor_id", "patient_code", name="uq_patients_doctor_id_patient_code"),
        # At most one "primary" patient per (doctor, phone): a guest record
        # (relationship NULL) or the account holder (SELF). Family members are
        # exempt so several can share the account holder's phone (docs/03 §8).
        Index(
            "uq_patients_doctor_primary_phone",
            "doctor_id",
            "phone_number",
            unique=True,
            postgresql_where=text("relationship IS NULL OR relationship = 'SELF'"),
        ),
        Index("ix_patients_doctor_id", "doctor_id"),
        Index("ix_patients_account_id", "account_id"),
        Index("ix_patients_phone_number", "phone_number"),
        Index("ix_patients_email", "email"),
    )
