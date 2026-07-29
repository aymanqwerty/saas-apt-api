import uuid
from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.exceptions import ApiException
from app.models.blog_category import BlogCategory
from app.models.gallery_post import GalleryPost, GalleryStatus
from app.repositories.blog_category_repository import BlogCategoryRepository
from app.repositories.gallery_repository import GalleryRepository
from app.schemas.gallery import (
    BlogCategoryCreate,
    BlogCategoryUpdate,
    GalleryPostCreate,
    GalleryPostUpdate,
)
from app.services.activity_log_service import ActivityLogService
from app.utils.sanitize import sanitize_html
from app.utils.slug import slugify


class GalleryService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._posts = GalleryRepository(db)
        self._categories = BlogCategoryRepository(db)
        self._activity = ActivityLogService(db)

    # -------------------------------------------------------------- categories
    def list_categories(self, doctor_id: uuid.UUID) -> list[BlogCategory]:
        return self._categories.list_for_doctor(doctor_id)

    def create_category(
        self, doctor_id: uuid.UUID, data: BlogCategoryCreate, request: Request | None = None
    ) -> BlogCategory:
        name = data.name.strip()

        # Typing the name of an existing category (rather than picking it from
        # the list) should reuse it, not create a near-duplicate.
        existing = self._categories.get_by_slug(doctor_id, slugify(name))
        if existing is not None:
            return existing

        category = BlogCategory(
            doctor_id=doctor_id, name=name, slug=self._unique_category_slug(doctor_id, name)
        )
        self._categories.add(category)
        self._activity.record(
            doctor_id, "CREATE_BLOG_CATEGORY", "BlogCategory", category.id, request=request
        )
        self._db.commit()
        self._db.refresh(category)
        return category

    def update_category(
        self,
        doctor_id: uuid.UUID,
        category_id: uuid.UUID,
        data: BlogCategoryUpdate,
        request: Request | None = None,
    ) -> BlogCategory:
        category = self._require_category(doctor_id, category_id)
        updates = data.model_dump(exclude_unset=True)

        if updates.get("name"):
            category.name = updates["name"].strip()
        if "display_order" in updates:
            category.display_order = updates["display_order"]

        self._activity.record(
            doctor_id, "UPDATE_BLOG_CATEGORY", "BlogCategory", category.id, request=request
        )
        self._db.commit()
        self._db.refresh(category)
        return category

    def delete_category(
        self, doctor_id: uuid.UUID, category_id: uuid.UUID, request: Request | None = None
    ) -> None:
        """Soft-delete a category; its posts become uncategorised rather than vanishing."""
        category = self._require_category(doctor_id, category_id)
        self._posts.clear_category(category.id)
        category.deleted_at = datetime.now(UTC)
        self._activity.record(
            doctor_id, "DELETE_BLOG_CATEGORY", "BlogCategory", category.id, request=request
        )
        self._db.commit()

    def _require_category(self, doctor_id: uuid.UUID, category_id: uuid.UUID) -> BlogCategory:
        category = self._categories.get_for_doctor(doctor_id, category_id)
        if category is None:
            raise ApiException(404, "Category not found", "NOT_FOUND")
        return category

    def _unique_category_slug(self, doctor_id: uuid.UUID, name: str) -> str:
        base = slugify(name) or "category"
        candidate = base
        suffix = 2
        while self._categories.slug_exists(doctor_id, candidate):
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    # ------------------------------------------------------------------ posts
    def list_posts(self, doctor_id: uuid.UUID) -> list[GalleryPost]:
        return self._posts.list_for_doctor(doctor_id)

    def get_post(self, doctor_id: uuid.UUID, post_id: uuid.UUID) -> GalleryPost:
        post = self._posts.get_for_doctor(doctor_id, post_id)
        if post is None:
            raise ApiException(404, "Blog post not found", "NOT_FOUND")
        return post

    @staticmethod
    def _clean_media(items: list[dict]) -> list[dict]:
        """Sanitise each item's rich-text description before it is stored."""
        cleaned = []
        for item in items:
            entry = dict(item)
            entry["description"] = sanitize_html(entry.get("description"))
            cleaned.append(entry)
        return cleaned

    def _unique_slug(self, doctor_id: uuid.UUID, title: str) -> str:
        base = slugify(title) or "post"
        candidate = base
        suffix = 2
        while self._posts.slug_exists(doctor_id, candidate):
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    def create_post(
        self, doctor_id: uuid.UUID, data: GalleryPostCreate, request: Request | None = None
    ) -> GalleryPost:
        if data.category_id is not None:
            self._require_category(doctor_id, data.category_id)

        now = datetime.now(UTC)
        post = GalleryPost(
            doctor_id=doctor_id,
            title=data.title,
            slug=self._unique_slug(doctor_id, data.title),
            introduction=data.introduction,
            body=sanitize_html(data.body),
            cover_image=data.cover_image,
            category_id=data.category_id,
            display_order=data.display_order,
            display_date=data.display_date,
            media=self._clean_media([item.model_dump() for item in data.media]),
            tags=data.tags,
            status=data.status,
        )
        if data.status == GalleryStatus.PUBLISHED:
            post.published_at = now
            # Default the card date to the publish date; the doctor can override.
            if post.display_date is None:
                post.display_date = now.date()

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
        if updates.get("category_id") is not None:
            self._require_category(doctor_id, updates["category_id"])
        if "media" in updates and updates["media"] is not None:
            updates["media"] = self._clean_media([dict(item) for item in updates["media"]])
        if "body" in updates:
            updates["body"] = sanitize_html(updates["body"])

        # The slug is intentionally NOT regenerated from a changed title —
        # links already shared with patients must keep working.
        newly_published = (
            "status" in updates
            and updates["status"] == GalleryStatus.PUBLISHED
            and post.status != GalleryStatus.PUBLISHED
        )

        for field, value in updates.items():
            setattr(post, field, value)

        if newly_published:
            now = datetime.now(UTC)
            if post.published_at is None:
                post.published_at = now
            if post.display_date is None:
                post.display_date = now.date()

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
