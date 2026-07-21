import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class DoctorStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUSPENDED = "SUSPENDED"


class Doctor(Base, TimestampMixin):
    __tablename__ = "doctors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str] = mapped_column(String(150))
    slug: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(Text)
    phone_number: Mapped[str] = mapped_column(String(20))
    profile_photo: Mapped[str | None] = mapped_column(Text)
    qualification: Mapped[str | None] = mapped_column(Text)
    specialization: Mapped[str] = mapped_column(String(150))
    experience_years: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    registration_number: Mapped[str | None] = mapped_column(String(100))
    about: Mapped[str | None] = mapped_column(Text)
    languages: Mapped[list[str] | None] = mapped_column(JSONB)
    # The doctor's bespoke public website origin (e.g. https://drsurbhi.com) —
    # used to build review/booking links the voice agent sends to patients.
    website_url: Mapped[str | None] = mapped_column(Text)
    # Secret the doctor's voice agent (ElevenLabs) presents to authenticate its
    # tool calls as this doctor. NULL until provisioned.
    agent_api_key: Mapped[str | None] = mapped_column(String(64))
    # The doctor's ElevenLabs agent id — used to mint a WebRTC conversation
    # token for their website voice widget.
    elevenlabs_agent_id: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[DoctorStatus] = mapped_column(
        SAEnum(DoctorStatus, name="doctor_status"),
        default=DoctorStatus.ACTIVE,
        server_default="ACTIVE",
    )
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # Unique among non-deleted doctors only (docs/04 §6): soft-deleted
        # doctors must not block their slug/email forever.
        Index(
            "uq_doctors_slug_active",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "uq_doctors_email_active",
            "email",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_doctors_status", "status"),
        Index(
            "uq_doctors_agent_api_key",
            "agent_api_key",
            unique=True,
            postgresql_where=text("agent_api_key IS NOT NULL"),
        ),
    )
