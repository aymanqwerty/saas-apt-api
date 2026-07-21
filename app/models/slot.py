import enum
import uuid
from datetime import date, time

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, Text, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Time as SATime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class SlotStatus(enum.StrEnum):
    AVAILABLE = "AVAILABLE"
    FULL = "FULL"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    EXPIRED = "EXPIRED"


class Slot(Base, TimestampMixin):
    __tablename__ = "slots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="RESTRICT")
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="RESTRICT")
    )
    availability_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("availability_rules.id", ondelete="SET NULL")
    )
    slot_date: Mapped[date] = mapped_column(Date)
    start_time: Mapped[time] = mapped_column(SATime)
    end_time: Mapped[time] = mapped_column(SATime)
    capacity: Mapped[int] = mapped_column(Integer)
    booked_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    status: Mapped[SlotStatus] = mapped_column(
        SAEnum(SlotStatus, name="slot_status"),
        default=SlotStatus.AVAILABLE,
        server_default="AVAILABLE",
    )
    is_manually_blocked: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    block_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_slots_doctor_id", "doctor_id"),
        Index("ix_slots_clinic_id", "clinic_id"),
        Index("ix_slots_slot_date", "slot_date"),
        Index("ix_slots_status", "status"),
        Index("ix_slots_clinic_id_slot_date", "clinic_id", "slot_date"),
        Index("ix_slots_doctor_id_slot_date", "doctor_id", "slot_date"),
    )
