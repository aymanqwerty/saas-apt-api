import enum
import uuid
from datetime import date, time

from sqlalchemy import Date, ForeignKey, Index, Integer, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Time as SATime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class Weekday(enum.StrEnum):
    MONDAY = "MONDAY"
    TUESDAY = "TUESDAY"
    WEDNESDAY = "WEDNESDAY"
    THURSDAY = "THURSDAY"
    FRIDAY = "FRIDAY"
    SATURDAY = "SATURDAY"
    SUNDAY = "SUNDAY"


# Python date.weekday(): Monday=0 .. Sunday=6
WEEKDAY_TO_PY = {
    Weekday.MONDAY: 0,
    Weekday.TUESDAY: 1,
    Weekday.WEDNESDAY: 2,
    Weekday.THURSDAY: 3,
    Weekday.FRIDAY: 4,
    Weekday.SATURDAY: 5,
    Weekday.SUNDAY: 6,
}


class AvailabilityRuleStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class AvailabilityRule(Base, TimestampMixin):
    __tablename__ = "availability_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="RESTRICT")
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT")
    )
    weekday: Mapped[Weekday] = mapped_column(SAEnum(Weekday, name="weekday"))
    start_time: Mapped[time] = mapped_column(SATime)
    end_time: Mapped[time] = mapped_column(SATime)
    slot_duration_minutes: Mapped[int] = mapped_column(Integer)
    patients_per_slot: Mapped[int] = mapped_column(Integer)
    buffer_minutes: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    effective_from: Mapped[date] = mapped_column(Date)
    effective_until: Mapped[date | None] = mapped_column(Date)
    status: Mapped[AvailabilityRuleStatus] = mapped_column(
        SAEnum(AvailabilityRuleStatus, name="availability_rule_status"),
        default=AvailabilityRuleStatus.ACTIVE,
        server_default="ACTIVE",
    )

    __table_args__ = (
        Index("ix_availability_rules_doctor_id", "doctor_id"),
        Index("ix_availability_rules_clinic_id", "clinic_id"),
        Index("ix_availability_rules_clinic_id_weekday", "clinic_id", "weekday"),
        Index("ix_availability_rules_status", "status"),
    )
