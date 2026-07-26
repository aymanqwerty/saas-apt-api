import enum
import uuid
from datetime import date, time
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date as SADate
from sqlalchemy import Enum as SAEnum
from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import Time as SATime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.patient import Patient


class AppointmentStatus(enum.StrEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"


class BookingSource(enum.StrEnum):
    WEBSITE = "WEBSITE"
    ADMIN = "ADMIN"
    VOICE_AGENT = "VOICE_AGENT"


class Appointment(Base, TimestampMixin):
    __tablename__ = "appointments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="RESTRICT")
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT")
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT")
    )
    slot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("slots.id", ondelete="RESTRICT")
    )
    appointment_number: Mapped[str] = mapped_column(String(20))
    token_number: Mapped[int] = mapped_column(Integer)
    appointment_status: Mapped[AppointmentStatus] = mapped_column(
        SAEnum(AppointmentStatus, name="appointment_status")
    )
    booking_source: Mapped[BookingSource] = mapped_column(
        SAEnum(BookingSource, name="booking_source")
    )
    visit_reason: Mapped[str | None] = mapped_column(Text)
    doctor_notes: Mapped[str | None] = mapped_column(Text)
    patient_notes: Mapped[str | None] = mapped_column(Text)
    cancellation_reason: Mapped[str | None] = mapped_column(Text)

    # Historical snapshots (docs/04 §14) — frozen at booking, updated only on reschedule.
    doctor_name: Mapped[str] = mapped_column(String(150))
    clinic_name: Mapped[str] = mapped_column(String(200))
    clinic_address: Mapped[str] = mapped_column(Text)
    consultation_fee: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    appointment_date: Mapped[date] = mapped_column(SADate)
    start_time: Mapped[time] = mapped_column(SATime)
    end_time: Mapped[time] = mapped_column(SATime)

    patient: Mapped["Patient"] = relationship("Patient", lazy="joined")

    __table_args__ = (
        UniqueConstraint("appointment_number", name="uq_appointments_appointment_number"),
        # A queue token is unique within a clinic-day; enforces no duplicate token
        # numbers under concurrent bookings (the service retries on collision).
        UniqueConstraint(
            "clinic_id",
            "appointment_date",
            "token_number",
            name="uq_appointments_clinic_date_token",
        ),
        Index("ix_appointments_doctor_id", "doctor_id"),
        Index("ix_appointments_clinic_id", "clinic_id"),
        Index("ix_appointments_patient_id", "patient_id"),
        Index("ix_appointments_slot_id", "slot_id"),
        Index("ix_appointments_appointment_status", "appointment_status"),
        Index("ix_appointments_doctor_id_status", "doctor_id", "appointment_status"),
        Index("ix_appointments_doctor_id_created_at", "doctor_id", "created_at"),
        # A patient may re-book a slot only after cancelling the prior appointment.
        Index(
            "uq_appointments_slot_patient_active",
            "slot_id",
            "patient_id",
            unique=True,
            postgresql_where=text("appointment_status != 'CANCELLED'"),
        ),
    )
