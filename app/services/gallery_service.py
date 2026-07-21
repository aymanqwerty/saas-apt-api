import uuid
from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.exceptions import ApiException
from app.models.gallery_post import GalleryPost, GalleryStatus
from app.repositories.gallery_repository import GalleryRepository
from app.schemas.gallery import GalleryPostCreate, GalleryPostUpdate
from app.services.activity_log_service import ActivityLogService
from app.utils.slug import slugify


class GalleryService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._posts = GalleryRepository(db)
        self._activity = ActivityLogService(db)

    def list_posts(self, doctor_id: uuid.UUID) -> list[GalleryPost]:
        return self._posts.list_for_doctor(doctor_id)

    def get_post(self, doctor_id: uuid.UUID, post_id: uuid.UUID) -> GalleryPost:
        post = self._posts.get_for_doctor(doctor_id, post_id)
        if post is None:
            raise ApiException(404, "Gallery post not found", "NOT_FOUND")
        return post

    def _unique_slug(self, doctor_id: uuid.UUID, title: str) -> str:
        base = slugify(title)
        candidate = base
        suffix = 2
        while self._posts.slug_exists(doctor_id, candidate):
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    def create_post(
        self, doctor_id: uuid.UUID, data: GalleryPostCreate, request: Request | None = None
    ) -> GalleryPost:
        post = GalleryPost(
            doctor_id=doctor_id,
            title=data.title,
            slug=self._unique_slug(doctor_id, data.title),
            description=data.description,
            category=data.category,
            media=[item.model_dump() for item in data.media],
            tags=data.tags,
            status=data.status,
        )
        if data.status == GalleryStatus.PUBLISHED:
            post.published_at = datetime.now(UTC)

        self._posts.add(post)
        self._activity.record(doctor_id, "CREATE_GALLERY", "GalleryPost", post.id, request=request)
        if data.status == GalleryStatus.PUBLISHED:
            self._activity.record(
                doctor_id, "GALLERY_PUBLISHED", "GalleryPost", post.id, request=request
            )
        self._db.commit()
        self._db.refresh(post)
        return post

    def update_post(
        self,
        doctor_id: uuid.UUID,
        post_id: uuid.UUID,
        data: GalleryPostUpdate,
        request: Request | None = None,
    ) -> GalleryPost:
        post = self.get_post(doctor_id, post_id)
        updates = data.model_dump(exclude_unset=True)

        if "title" in updates and updates["title"] is None:
            raise ApiException(422, "title cannot be empty", "VALIDATION_ERROR")
        if "media" in updates and updates["media"] is not None:
            updates["media"] = [dict(item) for item in updates["media"]]

        newly_published = (
            "status" in updates
            and updates["status"] == GalleryStatus.PUBLISHED
            and post.status != GalleryStatus.PUBLISHED
        )

        for field, value in updates.items():
            setattr(post, field, value)

        if newly_published and post.published_at is None:
            post.published_at = datetime.now(UTC)

        action = "GALLERY_PUBLISHED" if newly_published else "UPDATE_GALLERY"
        self._activity.record(doctor_id, action, "GalleryPost", post.id, request=request)
        self._db.commit()
        self._db.refresh(post)
        return post

    def delete_post(
        self, doctor_id: uuid.UUID, post_id: uuid.UUID, request: Request | None = None
    ) -> None:
        post = self.get_post(doctor_id, post_id)
        post.deleted_at = datetime.now(UTC)
        self._activity.record(doctor_id, "DELETE_GALLERY", "GalleryPost", post.id, request=request)
        self._db.commit()
