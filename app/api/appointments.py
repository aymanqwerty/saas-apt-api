import uuid
from datetime import date

from fastapi import APIRouter, Query, Request

from app.dependencies.auth import CurrentDoctor
from app.dependencies.database import DbSession
from app.models.appointment import AppointmentStatus
from app.schemas.appointment import (
    AppointmentDetail,
    AppointmentListItem,
    AppointmentUpdate,
)
from app.schemas.common import ApiResponse
from app.schemas.pagination import Page
from app.services.appointment_service import AppointmentService

router = APIRouter(prefix="/appointments")


@router.get("", response_model=ApiResponse[Page[AppointmentListItem]])
def list_appointments(
    doctor: CurrentDoctor,
    db: DbSession,
    status: AppointmentStatus | None = None,
    clinic_id: uuid.UUID | None = None,
    appointment_date: date | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    patient_name: str | None = None,
    appointment_number: str | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[Page[AppointmentListItem]]:
    service = AppointmentService(db)
    filters = service.parse_filters(
        status,
        clinic_id,
        appointment_date,
        date_from,
        date_to,
        patient_name,
        appointment_number,
    )
    items, total = service.list_appointments(doctor.id, filters, page, limit)
    return ApiResponse(
        data=Page.build([AppointmentListItem.from_model(a) for a in items], total, page, limit)
    )


@router.get("/{appointment_id}", response_model=ApiResponse[AppointmentDetail])
def get_appointment(
    appointment_id: uuid.UUID, doctor: CurrentDoctor, db: DbSession
) -> ApiResponse[AppointmentDetail]:
    appointment = AppointmentService(db).get_appointment(doctor.id, appointment_id)
    return ApiResponse(data=AppointmentDetail.from_model(appointment))


@router.patch("/{appointment_id}", response_model=ApiResponse[AppointmentDetail])
def update_appointment(
    appointment_id: uuid.UUID,
    body: AppointmentUpdate,
    doctor: CurrentDoctor,
    db: DbSession,
    request: Request,
) -> ApiResponse[AppointmentDetail]:
    appointment = AppointmentService(db).update_appointment(
        doctor.id, appointment_id, body, request=request
    )
    return ApiResponse(
        message="Appointment updated", data=AppointmentDetail.from_model(appointment)
    )
