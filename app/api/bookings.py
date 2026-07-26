import uuid

from fastapi import APIRouter, Request

from app.core.exceptions import ApiException
from app.core.rate_limit import booking_rate_limiter, get_client_ip
from app.dependencies.database import DbSession
from app.dependencies.patient_auth import OptionalAccount
from app.schemas.booking import (
    BookingConfirmation,
    BookingRequest,
    BookingStartResponse,
    ConfirmPaymentRequest,
)
from app.schemas.common import ApiResponse
from app.services.booking_service import BookingService

router = APIRouter(prefix="/public/bookings")


@router.post("", response_model=ApiResponse[BookingStartResponse], status_code=201)
def start_booking(
    body: BookingRequest, request: Request, db: DbSession, account: OptionalAccount
) -> ApiResponse[BookingStartResponse]:
    # Public write endpoint — rate-limited per IP and per account/phone (docs/12 §4).
    client_host = get_client_ip(request)
    rate_subject = str(account.id) if account is not None else body.phone_number
    if not booking_rate_limiter.is_allowed(f"{client_host}:{rate_subject}"):
        raise ApiException(
            429, "Too many booking attempts. Please try again shortly.", "RATE_LIMITED"
        )

    result = BookingService(db).start_booking(body, request=request, account=account)
    message = "Appointment booked" if result.status == "confirmed" else "Payment required"
    return ApiResponse(message=message, data=result)


@router.post("/{hold_id}/confirm", response_model=ApiResponse[BookingConfirmation])
def confirm_booking(
    hold_id: uuid.UUID, body: ConfirmPaymentRequest, request: Request, db: DbSession
) -> ApiResponse[BookingConfirmation]:
    confirmation = BookingService(db).confirm_booking(hold_id, body, request=request)
    return ApiResponse(message="Appointment booked", data=confirmation)


@router.post("/{hold_id}/release", response_model=ApiResponse[None])
def release_booking(hold_id: uuid.UUID, db: DbSession) -> ApiResponse[None]:
    BookingService(db).release_booking(hold_id)
    return ApiResponse(message="Reservation released", data=None)
