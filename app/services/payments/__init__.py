"""Payment provider factory — the single switch point for the gateway.

To change providers, add an implementation of `PaymentProvider` and return it
here based on `settings.payment_provider`. Nothing else in the app references a
concrete gateway.
"""

from app.core.config import settings
from app.services.payments.base import (
    PaymentError,
    PaymentLink,
    PaymentOrder,
    PaymentProvider,
    PaymentWebhookEvent,
)
from app.services.payments.razorpay_provider import RazorpayProvider

__all__ = [
    "PaymentError",
    "PaymentLink",
    "PaymentOrder",
    "PaymentProvider",
    "PaymentWebhookEvent",
    "get_payment_provider",
]


def get_payment_provider() -> PaymentProvider:
    provider = settings.payment_provider.lower()
    if provider == "razorpay":
        return RazorpayProvider(
            settings.razorpay_key_id,
            settings.razorpay_key_secret,
            settings.razorpay_webhook_secret,
        )
    raise PaymentError(f"Unknown payment provider: {settings.payment_provider}")
