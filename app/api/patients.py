import uuid

from fastapi import APIRouter, Query

from app.dependencies.auth import CurrentDoctor
from app.dependencies.database import DbSession
from app.schemas.appointment import AppointmentListItem
from app.schemas.common import ApiResponse
from app.schemas.pagination import Page
from app.schemas.patient import PatientDetail, PatientListItem
from app.services.patient_service import PatientService

router = APIRouter(prefix="/patients")


@router.get("", response_model=ApiResponse[Page[PatientListItem]])
def list_patients(
    doctor: CurrentDoctor,
    db: DbSession,
    search: str | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[Page[PatientListItem]]:
    items, total = PatientService(db).list_patients(doctor.id, search, page, limit)
    return ApiResponse(data=Page.build(items, total, page, limit))


@router.get("/{patient_id}", response_model=ApiResponse[PatientDetail])
def get_patient(
    patient_id: uuid.UUID, doctor: CurrentDoctor, db: DbSession
) -> ApiResponse[PatientDetail]:
    patient = PatientService(db).get_patient(doctor.id, patient_id)
    return ApiResponse(data=patient)


@router.get(
    "/{patient_id}/appointments",
    response_model=ApiResponse[list[AppointmentListItem]],
)
def get_patient_appointments(
    patient_id: uuid.UUID, doctor: CurrentDoctor, db: DbSession
) -> ApiResponse[list[AppointmentListItem]]:
    appointments = PatientService(db).list_patient_appointments(doctor.id, patient_id)
    return ApiResponse(data=[AppointmentListItem.from_model(a) for a in appointments])
