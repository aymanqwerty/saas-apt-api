import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class ClinicStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class Clinic(Base, TimestampMixin):
    __tablename__ = "clinics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="RESTRICT")
    )
    clinic_name: Mapped[str] = mapped_column(String(200))
    address_line_1: Mapped[str] = mapped_column(String(255))
    address_line_2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(100))
    country: Mapped[str] = mapped_column(String(100), default="India", server_default="India")
    postal_code: Mapped[str | None] = mapped_column(String(15))
    google_maps_url: Mapped[str | None] = mapped_column(Text)
    phone_number: Mapped[str | None] = mapped_column(String(20))
    consultation_fee: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    timezone: Mapped[str] = mapped_column(
        String(64), default="Asia/Kolkata", server_default="Asia/Kolkata"
    )
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ClinicStatus] = mapped_column(
        SAEnum(ClinicStatus, name="clinic_status"),
        default=ClinicStatus.ACTIVE,
        server_default="ACTIVE",
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_clinics_doctor_id", "doctor_id"),
        Index("ix_clinics_city", "city"),
        Index("ix_clinics_status", "status"),
        Index("ix_clinics_doctor_id_status", "doctor_id", "status"),
    )
