from fastapi import APIRouter

from app.dependencies.auth import CurrentDoctor
from app.dependencies.database import DbSession
from app.schemas.common import ApiResponse
from app.schemas.doctor import DoctorProfileUpdate, DoctorResponse
from app.services.profile_service import ProfileService

router = APIRouter(prefix="/doctors")


@router.get("/profile", response_model=ApiResponse[DoctorResponse])
def get_profile(doctor: CurrentDoctor) -> ApiResponse[DoctorResponse]:
    return ApiResponse(data=DoctorResponse.model_validate(doctor))


@router.patch("/profile", response_model=ApiResponse[DoctorResponse])
def update_profile(
    body: DoctorProfileUpdate, doctor: CurrentDoctor, db: DbSession
) -> ApiResponse[DoctorResponse]:
    updated = ProfileService(db).update_profile(doctor, body)
    return ApiResponse(message="Profile updated", data=DoctorResponse.model_validate(updated))
