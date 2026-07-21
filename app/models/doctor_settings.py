import uuid

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class DoctorSettings(Base, TimestampMixin):
    """One-to-one website configuration for a doctor (docs/04 §7)."""

    __tablename__ = "doctor_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="RESTRICT")
    )
    booking_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    gallery_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    show_consultation_fee: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    show_contact_information: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    # When true, website bookings require successful advance payment of the
    # selected clinic's consultation fee before the appointment is confirmed.
    payment_required: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    theme_color: Mapped[str | None] = mapped_column(String(20))
    custom_domain: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (UniqueConstraint("doctor_id", name="uq_doctor_settings_doctor_id"),)
