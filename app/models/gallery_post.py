import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin


class GalleryStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    HIDDEN = "HIDDEN"


class GalleryPost(Base, TimestampMixin):
    """A blog post in the doctor's "Success Stories" section.

    The section's public heading is doctor-configurable
    (`doctor_settings.section_label`); the URL segment is deliberately fixed so
    renaming the section never breaks links that patients have already been sent.
    """

    __tablename__ = "gallery_posts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="RESTRICT")
    )
    title: Mapped[str] = mapped_column(String(255))
    # Frozen once created: regenerating it from an edited title would silently
    # break every link already shared.
    slug: Mapped[str] = mapped_column(String(255))
    # Short teaser shown on the listing card.
    introduction: Mapped[str] = mapped_column(Text)
    # Long-form rich text (sanitised HTML). Optional so a post can be purely
    # a photo story.
    body: Mapped[str | None] = mapped_column(Text)
    cover_image: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("blog_categories.id", ondelete="SET NULL")
    )
    # Lower numbers surface first; NULL sorts last and falls back to date.
    display_order: Mapped[int | None] = mapped_column(Integer)
    # Shown on the card. Defaults to the publish date but is editable, so a
    # doctor can write up an operation that happened months ago.
    display_date: Mapped[date | None] = mapped_column(Date)
    media: Mapped[list | None] = mapped_column(JSONB)
    tags: Mapped[list | None] = mapped_column(JSONB)
    status: Mapped[GalleryStatus] = mapped_column(
        SAEnum(GalleryStatus, name="gallery_status"),
        default=GalleryStatus.DRAFT,
        server_default="DRAFT",
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    category = relationship("BlogCategory", lazy="joined")

    __table_args__ = (
        UniqueConstraint("doctor_id", "slug", name="uq_gallery_posts_doctor_id_slug"),
        Index("ix_gallery_posts_doctor_id", "doctor_id"),
        Index("ix_gallery_posts_status", "status"),
        Index("ix_gallery_posts_doctor_id_status", "doctor_id", "status"),
        Index("ix_gallery_posts_category_id", "category_id"),
    )
