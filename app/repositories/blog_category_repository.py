import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.blog_category import BlogCategory
from app.models.gallery_post import GalleryPost, GalleryStatus


class BlogCategoryRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_for_doctor(self, doctor_id: uuid.UUID) -> list[BlogCategory]:
        stmt = (
            select(BlogCategory)
            .where(BlogCategory.doctor_id == doctor_id, BlogCategory.deleted_at.is_(None))
            .order_by(
                BlogCategory.display_order.asc().nullslast(),
                BlogCategory.name.asc(),
            )
        )
        return list(self._db.scalars(stmt))

    def get_for_doctor(
        self, doctor_id: uuid.UUID, category_id: uuid.UUID
    ) -> BlogCategory | None:
        stmt = select(BlogCategory).where(
            BlogCategory.id == category_id,
            BlogCategory.doctor_id == doctor_id,
            BlogCategory.deleted_at.is_(None),
        )
        return self._db.scalar(stmt)

    def get_by_slug(self, doctor_id: uuid.UUID, slug: str) -> BlogCategory | None:
        stmt = select(BlogCategory).where(
            BlogCategory.doctor_id == doctor_id,
            BlogCategory.slug == slug,
            BlogCategory.deleted_at.is_(None),
        )
        return self._db.scalar(stmt)

    def slug_exists(self, doctor_id: uuid.UUID, slug: str) -> bool:
        return self.get_by_slug(doctor_id, slug) is not None

    def published_counts(self, doctor_id: uuid.UUID) -> dict[uuid.UUID, int]:
        """Published post count per category, for the public filter chips."""
        stmt = (
            select(GalleryPost.category_id, func.count())
            .where(
                GalleryPost.doctor_id == doctor_id,
                GalleryPost.status == GalleryStatus.PUBLISHED,
                GalleryPost.deleted_at.is_(None),
                GalleryPost.category_id.is_not(None),
            )
            .group_by(GalleryPost.category_id)
        )
        return {row[0]: row[1] for row in self._db.execute(stmt)}

    def add(self, category: BlogCategory) -> None:
        self._db.add(category)
        self._db.flush()
