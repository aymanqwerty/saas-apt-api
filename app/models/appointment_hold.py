import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class HoldStatus(enum.StrEnum):
    HELD = "HELD"  # seat reserved, awaiting payment
    CONFIRMED = "CONFIRMED"  # payment succeeded, appointment created
    EXPIRED = "EXPIRED"  # timed out or payment failed, seat released
    CANCELLED = "CANCELLED"  # patient abandoned checkout, seat released


class AppointmentHold(Base, TimestampMixin):
    """A temporary reservation of one slot seat while payment is in progress.

    A HELD row occupies one seat (via slots.booked_count) exactly like a
    confirmed booking, so a slot with capacity N allows at most N concurrent
    holds. On payment success it becomes CONFIRMED and an Appointment is
    created; on timeout/failure/abandon the seat is released (docs/03 §8).
    """

    __tablename__ = "appointment_holds"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="RESTRICT")
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT")
    )
    slot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("slots.id", ondelete="RESTRICT")
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT")
    )
    visit_reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[HoldStatus] = mapped_column(
        SAEnum(HoldStatus, name="hold_status"), default=HoldStatus.HELD
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_appointment_holds_slot_id", "slot_id"),
        # Drives the expiry sweep: find HELD holds past their deadline.
        Index("ix_appointment_holds_status_expires_at", "status", "expires_at"),
    )
