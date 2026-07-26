import uuid
from datetime import date

from fastapi import APIRouter, Query

from app.dependencies.auth import CurrentDoctor
from app.dependencies.database import DbSession
from app.models.payment import PaymentStatus
from app.repositories.payment_repository import PaymentRepository
from app.schemas.common import ApiResponse
from app.schemas.pagination import Page
from app.schemas.payment import PaymentListItem

router = APIRouter(prefix="/payments")


@router.get("", response_model=ApiResponse[Page[PaymentListItem]])
def list_payments(
    doctor: CurrentDoctor,
    db: DbSession,
    status: PaymentStatus | None = None,
    clinic_id: uuid.UUID | None = None,
    search: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> ApiResponse[Page[PaymentListItem]]:
    items, total = PaymentRepository(db).list_for_doctor(
        doctor.id,
        status=status,
        clinic_id=clinic_id,
        search=search,
        date_from=date_from,
        date_to=date_to,
        page=page,
        limit=limit,
    )
    return ApiResponse(
        data=Page.build([PaymentListItem.from_model(p) for p in items], total, page, limit)
    )
