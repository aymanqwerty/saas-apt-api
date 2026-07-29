import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.blog_category import BlogCategory
from app.models.gallery_post import GalleryPost, GalleryStatus


class GalleryRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    # Doctor-chosen order wins; posts without one fall back to date, newest
    # first. NULLS LAST keeps unordered posts below deliberately ordered ones.
    _ORDERING = (
        GalleryPost.display_order.asc().nullslast(),
        GalleryPost.display_date.desc().nullslast(),
        GalleryPost.published_at.desc().nullslast(),
        GalleryPost.created_at.desc(),
    )

    def count_published(self, doctor_id: uuid.UUID) -> int:
        return (
            self._db.scalar(
                select(func.count())
                .select_from(GalleryPost)
                .where(
                    GalleryPost.doctor_id == doctor_id,
                    GalleryPost.status == GalleryStatus.PUBLISHED,
                    GalleryPost.deleted_at.is_(None),
                )
            )
            or 0
        )

    def list_for_doctor(self, doctor_id: uuid.UUID) -> list[GalleryPost]:
        stmt = (
            select(GalleryPost)
            .where(GalleryPost.doctor_id == doctor_id, GalleryPost.deleted_at.is_(None))
            .order_by(*self._ORDERING)
        )
        return list(self._db.scalars(stmt))

    def get_for_doctor(self, doctor_id: uuid.UUID, post_id: uuid.UUID) -> GalleryPost | None:
        stmt = select(GalleryPost).where(
            GalleryPost.id == post_id,
            GalleryPost.doctor_id == doctor_id,
            GalleryPost.deleted_at.is_(None),
        )
        return self._db.scalar(stmt)

    def slug_exists(self, doctor_id: uuid.UUID, slug: str) -> bool:
        stmt = select(GalleryPost.id).where(
            GalleryPost.doctor_id == doctor_id,
            GalleryPost.slug == slug,
            GalleryPost.deleted_at.is_(None),
        )
        return self._db.scalar(stmt) is not None

    def _published_filters(self, doctor_id: uuid.UUID, category_slug: str | None):
        filters = [
            GalleryPost.doctor_id == doctor_id,
            GalleryPost.status == GalleryStatus.PUBLISHED,
            GalleryPost.deleted_at.is_(None),
        ]
        if category_slug:
            filters.append(BlogCategory.slug == category_slug)
        return filters

    def list_published_page(
        self,
        doctor_id: uuid.UUID,
        *,
        category_slug: str | None = None,
        page: int = 1,
        limit: int = 12,
    ) -> tuple[list[GalleryPost], int]:
        """One page of published posts, optionally filtered to a category."""
        filters = self._published_filters(doctor_id, category_slug)

        count_stmt = select(func.count()).select_from(GalleryPost)
        items_stmt = select(GalleryPost)
        if category_slug:
            count_stmt = count_stmt.join(BlogCategory, GalleryPost.category_id == BlogCategory.id)
            items_stmt = items_stmt.join(BlogCategory, GalleryPost.category_id == BlogCategory.id)

        total = self._db.scalar(count_stmt.where(*filters)) or 0
        items = list(
            self._db.scalars(
                items_stmt.where(*filters)
                .order_by(*self._ORDERING)
                .offset((page - 1) * limit)
                .limit(limit)
            )
        )
        return items, total

    def list_published(self, doctor_id: uuid.UUID, limit: int | None = None) -> list[GalleryPost]:
        stmt = (
            select(GalleryPost)
            .where(
                GalleryPost.doctor_id == doctor_id,
                GalleryPost.status == GalleryStatus.PUBLISHED,
                GalleryPost.deleted_at.is_(None),
            )
            .order_by(*self._ORDERING)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self._db.scalars(stmt))

    def get_published_by_slug(self, doctor_id: uuid.UUID, post_slug: str) -> GalleryPost | None:
        stmt = select(GalleryPost).where(
            GalleryPost.doctor_id == doctor_id,
            GalleryPost.slug == post_slug,
            GalleryPost.status == GalleryStatus.PUBLISHED,
            GalleryPost.deleted_at.is_(None),
        )
        return self._db.scalar(stmt)

    def clear_category(self, category_id: uuid.UUID) -> None:
        """Detach posts from a category being deleted (they become uncategorised)."""
        for post in self._db.scalars(
            select(GalleryPost).where(GalleryPost.category_id == category_id)
        ):
            post.category_id = None

    def add(self, post: GalleryPost) -> None:
        self._db.add(post)
        self._db.flush()
