import uuid
from datetime import date

from fastapi import APIRouter

from app.dependencies.auth import CurrentDoctor
from app.dependencies.database import DbSession
from app.models.slot import SlotStatus
from app.schemas.common import ApiResponse
from app.schemas.pagination import Page
from app.schemas.slot import SlotResponse, SlotUpdate
from app.services.slot_service import SlotService

from fastapi import APIRouter, Query

router = APIRouter(prefix="/slots")


@router.get("", response_model=ApiResponse[Page[SlotResponse]])
def list_slots(
    doctor: CurrentDoctor,
    db: DbSession,
    clinic_id: uuid.UUID | None = None,
    slot_date: date | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    status: SlotStatus | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[Page[SlotResponse]]:
    items, total = SlotService(db).list_slots(
        doctor.id,
        clinic_id=clinic_id,
        slot_date=slot_date,
        date_from=date_from,
        date_to=date_to,
        status=status,
        page=page,
        limit=limit,
    )
    return ApiResponse(
        data=Page.build([SlotResponse.model_validate(s) for s in items], total, page, limit)
    )


@router.patch("/{slot_id}", response_model=ApiResponse[SlotResponse])
def update_slot(
    slot_id: uuid.UUID, body: SlotUpdate, doctor: CurrentDoctor, db: DbSession
) -> ApiResponse[SlotResponse]:
    slot = SlotService(db).update_slot(doctor.id, slot_id, body)
    return ApiResponse(message="Slot updated", data=SlotResponse.model_validate(slot))
