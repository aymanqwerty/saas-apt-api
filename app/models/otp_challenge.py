import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class OtpPurpose(enum.StrEnum):
    AUTH = "AUTH"  # phone verification for login/registration


class OtpChallenge(Base, TimestampMixin):
    """A one-time passcode issued for a (doctor, phone) pair.

    The code is stored hashed. A challenge is spent once consumed, once its
    attempt budget is exhausted, or once it expires — whichever comes first.
    """

    __tablename__ = "otp_challenges"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE")
    )
    phone_number: Mapped[str] = mapped_column(String(20))
    code_hash: Mapped[str] = mapped_column(Text)
    purpose: Mapped[OtpPurpose] = mapped_column(
        SAEnum(OtpPurpose, name="otp_purpose"), default=OtpPurpose.AUTH
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_otp_challenges_doctor_id_phone_number", "doctor_id", "phone_number"),
    )
