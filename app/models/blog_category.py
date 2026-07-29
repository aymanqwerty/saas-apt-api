import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class BlogCategory(Base, TimestampMixin):
    """A per-doctor category for blog posts ("Success Stories" section).

    Scoped to a doctor so two doctors can both have a "Deliveries" category
    without collision. Soft-deleted: removing a category must not cascade into
    the posts that reference it, which instead fall back to uncategorised.
    """

    __tablename__ = "blog_categories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(100))
    # Controls the order of the filter chips on the public page.
    display_order: Mapped[int | None] = mapped_column()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("doctor_id", "slug", name="uq_blog_categories_doctor_id_slug"),
        Index("ix_blog_categories_doctor_id", "doctor_id"),
    )
