from fastapi import APIRouter, UploadFile

from app.dependencies.auth import CurrentDoctor
from app.schemas.common import ApiResponse
from app.schemas.media import MediaUploadData
from app.services.storage_service import LocalMediaStorage

router = APIRouter(prefix="/media")


@router.post("/upload", response_model=ApiResponse[MediaUploadData])
def upload_media(doctor: CurrentDoctor, file: UploadFile) -> ApiResponse[MediaUploadData]:
    url = LocalMediaStorage().save_image(str(doctor.id), file)
    return ApiResponse(message="File uploaded", data=MediaUploadData(url=url))
