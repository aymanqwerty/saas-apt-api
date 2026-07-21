import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class PaymentStatus(enum.StrEnum):
    PENDING = "PENDING"  # order created, awaiting payment
    PAID = "PAID"  # captured and verified
    FAILED = "FAILED"  # verification failed / abandoned / expired
    REFUNDED = "REFUNDED"  # reserved for the future refund flow (not built yet)


class Payment(Base, TimestampMixin):
    """A payment record for a website booking, one per hold that required payment.

    Patient/clinic names are snapshotted so the admin payment history is
    self-contained even for holds that never became appointments. The refund
    columns are unused for the MVP but let refunds be added without a migration.
    """

    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="RESTRICT")
    )
    hold_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointment_holds.id", ondelete="SET NULL")
    )
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id", ondelete="SET NULL")
    )
    patient_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="SET NULL")
    )
    # Kept alongside the clinic_name snapshot so payments are filterable by clinic.
    clinic_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="SET NULL")
    )

    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(PaymentStatus, name="payment_status"), default=PaymentStatus.PENDING
    )

    # Provider-agnostic references (Razorpay today, swappable interface).
    provider: Mapped[str] = mapped_column(String(50), default="razorpay")
    provider_order_id: Mapped[str | None] = mapped_column(String(255))
    provider_payment_id: Mapped[str | None] = mapped_column(String(255))
    provider_signature: Mapped[str | None] = mapped_column(Text)

    # Snapshots for a self-contained payment history.
    patient_name: Mapped[str] = mapped_column(String(150))
    clinic_name: Mapped[str] = mapped_column(String(200))

    failure_reason: Mapped[str | None] = mapped_column(Text)
    refund_id: Mapped[str | None] = mapped_column(String(255))
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_payments_doctor_id", "doctor_id"),
        Index("ix_payments_doctor_id_created_at", "doctor_id", "created_at"),
        Index("ix_payments_provider_order_id", "provider_order_id"),
        Index("ix_payments_clinic_id", "clinic_id"),
    )
