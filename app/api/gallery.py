import uuid

from fastapi import APIRouter, Request

from app.dependencies.auth import CurrentDoctor
from app.dependencies.database import DbSession
from app.schemas.common import ApiResponse
from app.schemas.gallery import (
    GalleryPostCreate,
    GalleryPostResponse,
    GalleryPostUpdate,
)
from app.services.gallery_service import GalleryService

router = APIRouter(prefix="/gallery")


@router.get("", response_model=ApiResponse[list[GalleryPostResponse]])
def list_gallery(doctor: CurrentDoctor, db: DbSession) -> ApiResponse[list[GalleryPostResponse]]:
    posts = GalleryService(db).list_posts(doctor.id)
    return ApiResponse(data=[GalleryPostResponse.model_validate(p) for p in posts])


@router.post("", response_model=ApiResponse[GalleryPostResponse], status_code=201)
def create_gallery(
    body: GalleryPostCreate, doctor: CurrentDoctor, db: DbSession, request: Request
) -> ApiResponse[GalleryPostResponse]:
    post = GalleryService(db).create_post(doctor.id, body, request=request)
    return ApiResponse(
        message="Gallery post created", data=GalleryPostResponse.model_validate(post)
    )


@router.get("/{post_id}", response_model=ApiResponse[GalleryPostResponse])
def get_gallery(
    post_id: uuid.UUID, doctor: CurrentDoctor, db: DbSession
) -> ApiResponse[GalleryPostResponse]:
    post = GalleryService(db).get_post(doctor.id, post_id)
    return ApiResponse(data=GalleryPostResponse.model_validate(post))


@router.patch("/{post_id}", response_model=ApiResponse[GalleryPostResponse])
def update_gallery(
    post_id: uuid.UUID,
    body: GalleryPostUpdate,
    doctor: CurrentDoctor,
    db: DbSession,
    request: Request,
) -> ApiResponse[GalleryPostResponse]:
    post = GalleryService(db).update_post(doctor.id, post_id, body, request=request)
    return ApiResponse(
        message="Gallery post updated", data=GalleryPostResponse.model_validate(post)
    )


@router.delete("/{post_id}", response_model=ApiResponse[None])
def delete_gallery(
    post_id: uuid.UUID, doctor: CurrentDoctor, db: DbSession, request: Request
) -> ApiResponse[None]:
    GalleryService(db).delete_post(doctor.id, post_id, request=request)
    return ApiResponse(message="Gallery post deleted", data=None)
