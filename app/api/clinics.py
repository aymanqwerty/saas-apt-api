import uuid

from fastapi import APIRouter, Request

from app.dependencies.auth import CurrentDoctor
from app.dependencies.database import DbSession
from app.models.clinic import ClinicStatus
from app.schemas.clinic import ClinicCreate, ClinicResponse, ClinicUpdate
from app.schemas.common import ApiResponse
from app.services.clinic_service import ClinicService

router = APIRouter(prefix="/clinics")


@router.get("", response_model=ApiResponse[list[ClinicResponse]])
def list_clinics(
    doctor: CurrentDoctor,
    db: DbSession,
    search: str | None = None,
    status: ClinicStatus | None = None,
) -> ApiResponse[list[ClinicResponse]]:
    clinics = ClinicService(db).list_clinics(doctor.id, search=search, status=status)
    return ApiResponse(data=[ClinicResponse.model_validate(c) for c in clinics])


@router.post("", response_model=ApiResponse[ClinicResponse], status_code=201)
def create_clinic(
    body: ClinicCreate, doctor: CurrentDoctor, db: DbSession, request: Request
) -> ApiResponse[ClinicResponse]:
    clinic = ClinicService(db).create_clinic(doctor.id, body, request=request)
    return ApiResponse(message="Clinic created", data=ClinicResponse.model_validate(clinic))


@router.get("/{clinic_id}", response_model=ApiResponse[ClinicResponse])
def get_clinic(
    clinic_id: uuid.UUID, doctor: CurrentDoctor, db: DbSession
) -> ApiResponse[ClinicResponse]:
    clinic = ClinicService(db).get_clinic(doctor.id, clinic_id)
    return ApiResponse(data=ClinicResponse.model_validate(clinic))


@router.patch("/{clinic_id}", response_model=ApiResponse[ClinicResponse])
def update_clinic(
    clinic_id: uuid.UUID,
    body: ClinicUpdate,
    doctor: CurrentDoctor,
    db: DbSession,
    request: Request,
) -> ApiResponse[ClinicResponse]:
    clinic = ClinicService(db).update_clinic(doctor.id, clinic_id, body, request=request)
    return ApiResponse(message="Clinic updated", data=ClinicResponse.model_validate(clinic))


@router.delete("/{clinic_id}", response_model=ApiResponse[None])
def delete_clinic(
    clinic_id: uuid.UUID, doctor: CurrentDoctor, db: DbSession, request: Request
) -> ApiResponse[None]:
    ClinicService(db).delete_clinic(doctor.id, clinic_id, request=request)
    return ApiResponse(message="Clinic deleted", data=None)
