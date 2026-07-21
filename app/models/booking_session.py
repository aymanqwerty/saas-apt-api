import enum
import uuid
from datetime import date, datetime, time

from sqlalchemy import Date as SADate
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Time as SATime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin
from app.models.patient import Gender


class BookingSessionStatus(enum.StrEnum):
    DRAFT = "DRAFT"  # captured, awaiting the patient to review & book
    CONSUMED = "CONSUMED"  # patient completed the booking from this draft
    EXPIRED = "EXPIRED"


class BookingSession(Base, TimestampMixin):
    """A pre-filled booking draft created by the voice agent (or any channel).

    Holds the details captured during a conversation so the patient can open a
    link, review/edit them, and complete the booking on the website. It does NOT
    reserve a seat — the reservation happens when the patient proceeds to book.
    """

    __tablename__ = "booking_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Opaque token used in the review URL (not guessable).
    token: Mapped[str] = mapped_column(String(48))
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE")
    )
    clinic_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="SET NULL")
    )
    slot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("slots.id", ondelete="SET NULL")
    )

    # Captured patient details (guest-style; identity resolved by phone on book).
    name: Mapped[str] = mapped_column(String(150))
    phone_number: Mapped[str] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(255))
    age: Mapped[int | None] = mapped_column(Integer)
    gender: Mapped[Gender | None] = mapped_column(SAEnum(Gender, name="gender"))
    reason: Mapped[str | None] = mapped_column(Text)

    # Snapshots for display on the review page (slot may change/expire meanwhile).
    clinic_name: Mapped[str | None] = mapped_column(String(200))
    slot_date: Mapped[date | None] = mapped_column(SADate)
    start_time: Mapped[time | None] = mapped_column(SATime)
    end_time: Mapped[time | None] = mapped_column(SATime)

    status: Mapped[BookingSessionStatus] = mapped_column(
        SAEnum(BookingSessionStatus, name="booking_session_status"),
        default=BookingSessionStatus.DRAFT,
    )
    source: Mapped[str] = mapped_column(String(30), default="VOICE_AGENT")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("uq_booking_sessions_token", "token", unique=True),
        Index("ix_booking_sessions_doctor_id", "doctor_id"),
    )
