import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.gallery_post import GalleryStatus
from app.utils.instagram import instagram_embed
from app.utils.sanitize import strip_html
from app.utils.youtube import youtube_video_id

# "video" is a file we host ourselves; "youtube"/"instagram" are embeds.
MediaType = Literal["image", "video", "youtube", "instagram"]


def _require_web_url(value: str) -> str:
    """Reject anything that isn't http(s).

    These URLs land in href/src on patient-facing pages, so allowing
    `javascript:` here would let a compromised doctor account run script in a
    patient's browser.
    """
    candidate = value.strip()
    if not candidate:
        raise ValueError("URL cannot be empty")
    lowered = candidate.lower()
    if lowered.startswith("/"):
        # Relative path from our own media storage — safe.
        return candidate
    if not lowered.startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://")
    return candidate


class MediaItem(BaseModel):
    type: MediaType
    url: str = Field(min_length=1)
    # Rich text (sanitised server-side) so a doctor can write as much as they
    # want under an image. Alt text is derived from it as plain text.
    description: str | None = Field(default=None, max_length=20_000)

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        return _require_web_url(value)

    @model_validator(mode="after")
    def _validate_youtube(self) -> "MediaItem":
        if self.type == "youtube" and youtube_video_id(self.url) is None:
            raise ValueError("Could not read a YouTube video id from that link")
        return self


class MediaItemOut(MediaItem):
    """Adds derived fields so the client never parses URLs or HTML itself."""

    youtube_id: str | None = None
    # Instagram shortcode + kind ("p" | "reel" | "tv"). None when the link
    # isn't an embeddable post — a profile or story link, say — in which case
    # the client shows a plain link instead of an embed.
    instagram_id: str | None = None
    instagram_kind: str | None = None
    # Plain-text form of `description`, for alt attributes and previews —
    # alt text cannot contain markup.
    description_text: str | None = None

    @classmethod
    def from_stored(cls, item: dict) -> "MediaItemOut":
        media_type = item.get("type", "image")
        url = item.get("url", "")
        description = item.get("description")

        embed = instagram_embed(url) if media_type == "instagram" else None
        return cls(
            type=media_type,
            url=url,
            description=description,
            description_text=strip_html(description),
            youtube_id=youtube_video_id(url) if media_type == "youtube" else None,
            instagram_kind=embed[0] if embed else None,
            instagram_id=embed[1] if embed else None,
        )


# --------------------------------------------------------------- categories
class BlogCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class BlogCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    display_order: int | None = None


class BlogCategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    display_order: int | None


class PublicBlogCategory(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    slug: str
    post_count: int = 0


# -------------------------------------------------------------------- posts
class GalleryPostCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    introduction: str = Field(min_length=1)
    body: str | None = None
    cover_image: str | None = None
    category_id: uuid.UUID | None = None
    display_order: int | None = Field(default=None, ge=0)
    display_date: date | None = None
    media: list[MediaItem] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    status: GalleryStatus = GalleryStatus.DRAFT

    @field_validator("cover_image")
    @classmethod
    def _validate_cover(cls, value: str | None) -> str | None:
        return _require_web_url(value) if value else value


class GalleryPostUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    introduction: str | None = Field(default=None, min_length=1)
    body: str | None = None
    cover_image: str | None = None
    category_id: uuid.UUID | None = None
    display_order: int | None = Field(default=None, ge=0)
    display_date: date | None = None
    media: list[MediaItem] | None = None
    tags: list[str] | None = None
    status: GalleryStatus | None = None

    @field_validator("cover_image")
    @classmethod
    def _validate_cover(cls, value: str | None) -> str | None:
        return _require_web_url(value) if value else value


class GalleryPostResponse(BaseModel):
    """Admin-facing shape — includes drafts and the full body."""

    id: uuid.UUID
    title: str
    slug: str
    introduction: str
    body: str | None
    cover_image: str | None
    category_id: uuid.UUID | None
    category_name: str | None
    display_order: int | None
    display_date: date | None
    media: list[MediaItemOut]
    tags: list[str]
    status: GalleryStatus
    published_at: datetime | None
    created_at: datetime

    @classmethod
    def from_post(cls, post) -> "GalleryPostResponse":
        return cls(
            id=post.id,
            title=post.title,
            slug=post.slug,
            introduction=post.introduction,
            body=post.body,
            cover_image=post.cover_image,
            category_id=post.category_id,
            category_name=post.category.name if post.category else None,
            display_order=post.display_order,
            display_date=post.display_date,
            media=[MediaItemOut.from_stored(item) for item in (post.media or [])],
            tags=post.tags or [],
            status=post.status,
            published_at=post.published_at,
            created_at=post.created_at,
        )


class PublicGalleryItem(BaseModel):
    """Listing card: cover, date badge, title, teaser."""

    id: uuid.UUID
    title: str
    slug: str
    introduction: str
    cover_image: str | None
    category_name: str | None
    category_slug: str | None
    display_date: date | None
    published_at: datetime | None

    @classmethod
    def from_post(cls, post) -> "PublicGalleryItem":
        return cls(
            id=post.id,
            title=post.title,
            slug=post.slug,
            introduction=post.introduction,
            cover_image=post.cover_image,
            category_name=post.category.name if post.category else None,
            category_slug=post.category.slug if post.category else None,
            display_date=post.display_date,
            published_at=post.published_at,
        )


class PublicGalleryDetail(BaseModel):
    title: str
    slug: str
    introduction: str
    body: str | None
    cover_image: str | None
    category_name: str | None
    category_slug: str | None
    display_date: date | None
    media: list[MediaItemOut]
    tags: list[str]
    published_at: datetime | None

    @classmethod
    def from_post(cls, post) -> "PublicGalleryDetail":
        return cls(
            title=post.title,
            slug=post.slug,
            introduction=post.introduction,
            body=post.body,
            cover_image=post.cover_image,
            category_name=post.category.name if post.category else None,
            category_slug=post.category.slug if post.category else None,
            display_date=post.display_date,
            media=[MediaItemOut.from_stored(item) for item in (post.media or [])],
            tags=post.tags or [],
            published_at=post.published_at,
        )
