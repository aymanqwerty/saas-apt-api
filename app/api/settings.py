from fastapi import APIRouter

from app.dependencies.auth import CurrentDoctor
from app.dependencies.database import DbSession
from app.schemas.common import ApiResponse
from app.schemas.settings import SettingsResponse, SettingsUpdate
from app.services.settings_service import SettingsService

router = APIRouter(prefix="/settings")


@router.get("", response_model=ApiResponse[SettingsResponse])
def get_settings(doctor: CurrentDoctor, db: DbSession) -> ApiResponse[SettingsResponse]:
    settings = SettingsService(db).get_or_create(doctor.id)
    return ApiResponse(data=SettingsResponse.model_validate(settings))


@router.patch("", response_model=ApiResponse[SettingsResponse])
def update_settings(
    body: SettingsUpdate, doctor: CurrentDoctor, db: DbSession
) -> ApiResponse[SettingsResponse]:
    settings = SettingsService(db).update(doctor.id, body)
    return ApiResponse(message="Settings updated", data=SettingsResponse.model_validate(settings))
