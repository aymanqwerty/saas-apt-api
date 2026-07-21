import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.gallery_post import GalleryStatus


class MediaItem(BaseModel):
    type: Literal["image", "youtube", "instagram"]
    url: str = Field(min_length=1)


class GalleryPostCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    category: str | None = Field(default=None, max_length=100)
    media: list[MediaItem] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    status: GalleryStatus = GalleryStatus.DRAFT


class GalleryPostUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1)
    category: str | None = Field(default=None, max_length=100)
    media: list[MediaItem] | None = None
    tags: list[str] | None = None
    status: GalleryStatus | None = None


class GalleryPostResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    slug: str
    description: str
    category: str | None
    media: list[MediaItem]
    tags: list[str]
    status: GalleryStatus
    published_at: datetime | None
    created_at: datetime


class PublicGalleryItem(BaseModel):
    id: uuid.UUID
    title: str
    slug: str
    category: str | None
    thumbnail: str | None
    published_at: datetime | None


class PublicGalleryDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    slug: str
    description: str
    category: str | None
    media: list[MediaItem]
    tags: list[str]
    published_at: datetime | None
