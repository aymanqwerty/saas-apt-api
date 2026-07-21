import enum
import uuid
from datetime import date, time

from sqlalchemy import Boolean, Date, ForeignKey, Index, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Time as SATime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class ExceptionType(enum.StrEnum):
    HOLIDAY = "HOLIDAY"
    LEAVE = "LEAVE"
    CUSTOM = "CUSTOM"
    BLOCKED = "BLOCKED"


class AvailabilityException(Base, TimestampMixin):
    """Overrides recurring availability on a specific date (docs/04 §11).

    clinic_id NULL applies to every clinic; a clinic-specific exception takes
    precedence over a doctor-wide one for that clinic (docs/03 §6).
    """

    __tablename__ = "availability_exceptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="RESTRICT")
    )
    clinic_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT")
    )
    exception_date: Mapped[date] = mapped_column(Date)
    exception_type: Mapped[ExceptionType] = mapped_column(
        SAEnum(ExceptionType, name="exception_type")
    )
    is_available: Mapped[bool] = mapped_column(Boolean)
    custom_start_time: Mapped[time | None] = mapped_column(SATime)
    custom_end_time: Mapped[time | None] = mapped_column(SATime)
    reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_availability_exceptions_doctor_id", "doctor_id"),
        Index("ix_availability_exceptions_exception_date", "exception_date"),
    )
