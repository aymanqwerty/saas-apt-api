import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.gallery_post import GalleryPost, GalleryStatus


class GalleryRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

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
            .order_by(GalleryPost.created_at.desc())
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

    def list_published(self, doctor_id: uuid.UUID) -> list[GalleryPost]:
        stmt = (
            select(GalleryPost)
            .where(
                GalleryPost.doctor_id == doctor_id,
                GalleryPost.status == GalleryStatus.PUBLISHED,
                GalleryPost.deleted_at.is_(None),
            )
            .order_by(GalleryPost.published_at.desc())
        )
        return list(self._db.scalars(stmt))

    def get_published_by_slug(self, doctor_id: uuid.UUID, post_slug: str) -> GalleryPost | None:
        stmt = select(GalleryPost).where(
            GalleryPost.doctor_id == doctor_id,
            GalleryPost.slug == post_slug,
            GalleryPost.status == GalleryStatus.PUBLISHED,
            GalleryPost.deleted_at.is_(None),
        )
        return self._db.scalar(stmt)

    def add(self, post: GalleryPost) -> None:
        self._db.add(post)
        self._db.flush()
