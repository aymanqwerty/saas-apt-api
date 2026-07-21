import json
import logging

from fastapi import APIRouter, Depends, Request

from app.core.exceptions import ApiException
from app.dependencies.database import DbSession
from app.schemas.common import ApiResponse
from app.services.booking_service import BookingService
from app.services.payments import PaymentError, PaymentProvider, get_payment_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks")


def get_webhook_provider() -> PaymentProvider:
    """Overridable in tests so the paid webhook can be exercised without Razorpay."""
    return get_payment_provider()


@router.post("/razorpay", response_model=ApiResponse[None])
async def razorpay_webhook(
    request: Request,
    db: DbSession,
    provider: PaymentProvider = Depends(get_webhook_provider),
) -> ApiResponse[None]:
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    try:
        valid = provider.verify_webhook(body, signature)
    except PaymentError:
        raise ApiException(400, "Webhook is not configured", "WEBHOOK_NOT_CONFIGURED") from None
    if not valid:
        raise ApiException(400, "Invalid webhook signature", "INVALID_SIGNATURE")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise ApiException(400, "Malformed webhook body", "VALIDATION_ERROR") from None

    event = provider.parse_webhook(payload)
    if event.kind == "paid" and event.payment_id:
        service = BookingService(db)
        if event.hold_id:
            service.confirm_hold_payment(event.hold_id, event.payment_id, request=request)
            logger.info("Processed payment webhook for hold %s", event.hold_id)
        elif event.link_id:
            service.confirm_payment_link(event.link_id, event.payment_id, request=request)
            logger.info("Processed payment-link webhook for link %s", event.link_id)

    return ApiResponse(message="ok", data=None)
