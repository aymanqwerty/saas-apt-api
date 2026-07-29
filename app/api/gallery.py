import uuid

from fastapi import APIRouter, Request

from app.dependencies.auth import CurrentDoctor
from app.dependencies.database import DbSession
from app.schemas.common import ApiResponse
from app.schemas.gallery import (
    BlogCategoryCreate,
    BlogCategoryResponse,
    BlogCategoryUpdate,
    GalleryPostCreate,
    GalleryPostResponse,
    GalleryPostUpdate,
)
from app.services.gallery_service import GalleryService

router = APIRouter(prefix="/gallery")


# --------------------------------------------------------------- categories
# Declared before /{post_id} so "categories" is never parsed as a post UUID.
@router.get("/categories", response_model=ApiResponse[list[BlogCategoryResponse]])
def list_categories(
    doctor: CurrentDoctor, db: DbSession
) -> ApiResponse[list[BlogCategoryResponse]]:
    categories = GalleryService(db).list_categories(doctor.id)
    return ApiResponse(data=[BlogCategoryResponse.model_validate(c) for c in categories])


@router.post("/categories", response_model=ApiResponse[BlogCategoryResponse], status_code=201)
def create_category(
    body: BlogCategoryCreate, doctor: CurrentDoctor, db: DbSession, request: Request
) -> ApiResponse[BlogCategoryResponse]:
    category = GalleryService(db).create_category(doctor.id, body, request=request)
    return ApiResponse(
        message="Category saved", data=BlogCategoryResponse.model_validate(category)
    )


@router.patch("/categories/{category_id}", response_model=ApiResponse[BlogCategoryResponse])
def update_category(
    category_id: uuid.UUID,
    body: BlogCategoryUpdate,
    doctor: CurrentDoctor,
    db: DbSession,
    request: Request,
) -> ApiResponse[BlogCategoryResponse]:
    category = GalleryService(db).update_category(doctor.id, category_id, body, request=request)
    return ApiResponse(
        message="Category updated", data=BlogCategoryResponse.model_validate(category)
    )


@router.delete("/categories/{category_id}", response_model=ApiResponse[None])
def delete_category(
    category_id: uuid.UUID, doctor: CurrentDoctor, db: DbSession, request: Request
) -> ApiResponse[None]:
    GalleryService(db).delete_category(doctor.id, category_id, request=request)
    return ApiResponse(message="Category deleted", data=None)


# -------------------------------------------------------------------- posts
@router.get("", response_model=ApiResponse[list[GalleryPostResponse]])
def list_gallery(doctor: CurrentDoctor, db: DbSession) -> ApiResponse[list[GalleryPostResponse]]:
    posts = GalleryService(db).list_posts(doctor.id)
    return ApiResponse(data=[GalleryPostResponse.from_post(p) for p in posts])


@router.post("", response_model=ApiResponse[GalleryPostResponse], status_code=201)
def create_gallery(
    body: GalleryPostCreate, doctor: CurrentDoctor, db: DbSession, request: Request
) -> ApiResponse[GalleryPostResponse]:
    post = GalleryService(db).create_post(doctor.id, body, request=request)
    return ApiResponse(message="Blog post created", data=GalleryPostResponse.from_post(post))


@router.get("/{post_id}", response_model=ApiResponse[GalleryPostResponse])
def get_gallery(
    post_id: uuid.UUID, doctor: CurrentDoctor, db: DbSession
) -> ApiResponse[GalleryPostResponse]:
    post = GalleryService(db).get_post(doctor.id, post_id)
    return ApiResponse(data=GalleryPostResponse.from_post(post))


@router.patch("/{post_id}", response_model=ApiResponse[GalleryPostResponse])
def update_gallery(
    post_id: uuid.UUID,
    body: GalleryPostUpdate,
    doctor: CurrentDoctor,
    db: DbSession,
    request: Request,
) -> ApiResponse[GalleryPostResponse]:
    post = GalleryService(db).update_post(doctor.id, post_id, body, request=request)
    return ApiResponse(message="Blog post updated", data=GalleryPostResponse.from_post(post))


@router.delete("/{post_id}", response_model=ApiResponse[None])
def delete_gallery(
    post_id: uuid.UUID, doctor: CurrentDoctor, db: DbSession, request: Request
) -> ApiResponse[None]:
    GalleryService(db).delete_post(doctor.id, post_id, request=request)
    return ApiResponse(message="Blog post deleted", data=None)
