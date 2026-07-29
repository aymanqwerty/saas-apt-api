import logging

from fastapi import APIRouter, UploadFile

from app.core.exceptions import ApiException
from app.dependencies.auth import CurrentDoctor
from app.schemas.common import ApiResponse
from app.schemas.media import MediaUploadData
from app.services.storage_service import StorageError, get_media_storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/media")


@router.post("/upload", response_model=ApiResponse[MediaUploadData])
def upload_media(doctor: CurrentDoctor, file: UploadFile) -> ApiResponse[MediaUploadData]:
    try:
        url = get_media_storage().save_image(str(doctor.id), file)
    except StorageError as exc:
        # Misconfiguration or a backing-store outage — not the caller's fault.
        logger.error("Media storage unavailable: %s", exc)
        raise ApiException(
            502, "Could not store the image right now. Please try again.", "STORAGE_UNAVAILABLE"
        ) from exc
    return ApiResponse(message="File uploaded", data=MediaUploadData(url=url))


@router.post("/upload-video", response_model=ApiResponse[MediaUploadData])
def upload_video(doctor: CurrentDoctor, file: UploadFile) -> ApiResponse[MediaUploadData]:
    """Separate from /upload because videos have their own types and size cap."""
    try:
        url = get_media_storage().save_video(str(doctor.id), file)
    except StorageError as exc:
        logger.error("Media storage unavailable: %s", exc)
        raise ApiException(
            502, "Could not store the video right now. Please try again.", "STORAGE_UNAVAILABLE"
        ) from exc
    return ApiResponse(message="Video uploaded", data=MediaUploadData(url=url))
