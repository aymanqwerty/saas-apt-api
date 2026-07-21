"""Razorpay implementation of the PaymentProvider interface.

All Razorpay-specific details (SDK, order shape, signature scheme) are confined
to this file. The `razorpay` package is imported lazily so the app still boots
when the gateway is unconfigured — errors surface only when a paid booking is
actually attempted.
"""

import logging
from decimal import Decimal

from app.services.payments.base import (
    PaymentError,
    PaymentLink,
    PaymentOrder,
    PaymentWebhookEvent,
)

logger = logging.getLogger(__name__)


def _to_minor_units(amount: Decimal) -> int:
    """Rupees -> paise. Razorpay works in the smallest currency unit."""
    return int((amount * 100).to_integral_value())


def _clean_contact(phone: str) -> str:
    """Reduce a phone to digits (keeping a leading + if present) for Razorpay."""
    has_plus = phone.strip().startswith("+")
    digits = "".join(c for c in phone if c.isdigit())
    return f"+{digits}" if has_plus else digits


class RazorpayProvider:
    name = "razorpay"

    def __init__(self, key_id: str, key_secret: str, webhook_secret: str = "") -> None:
        self._key_id = key_id
        self._key_secret = key_secret
        self._webhook_secret = webhook_secret

    def _client(self):
        if not self._key_id or not self._key_secret:
            raise PaymentError("Razorpay credentials are not configured")
        try:
            import razorpay
        except ImportError as exc:  # pragma: no cover - dependency missing
            raise PaymentError("razorpay package is not installed") from exc
        return razorpay.Client(auth=(self._key_id, self._key_secret))

    def create_order(self, amount: Decimal, currency: str, receipt: str) -> PaymentOrder:
        minor = _to_minor_units(amount)
        try:
            order = self._client().order.create(
                {
                    "amount": minor,
                    "currency": currency,
                    "receipt": receipt,
                    "payment_capture": 1,
                }
            )
        except PaymentError:
            raise
        except Exception as exc:
            logger.exception("Razorpay order creation failed")
            raise PaymentError("Could not create payment order") from exc
        return PaymentOrder(order_id=order["id"], amount=minor, currency=currency)

    def verify_payment(self, order_id: str, payment_id: str, signature: str) -> bool:
        import razorpay

        try:
            self._client().utility.verify_payment_signature(
                {
                    "razorpay_order_id": order_id,
                    "razorpay_payment_id": payment_id,
                    "razorpay_signature": signature,
                }
            )
            return True
        except razorpay.errors.SignatureVerificationError:
            return False

    def create_payment_link(
        self,
        amount: Decimal,
        currency: str,
        *,
        receipt: str,
        description: str,
        customer_name: str,
        customer_phone: str,
        expire_by_epoch: int | None = None,
    ) -> PaymentLink:
        base: dict = {
            "amount": _to_minor_units(amount),
            "currency": currency,
            "description": description,
            "notify": {"sms": False, "email": False},  # we send it ourselves
            "reminder_enable": False,
            # hold_id lets us correlate the payment.captured webhook back to the
            # booking. Razorpay copies payment-link notes onto the payment.
            "notes": {"hold_id": receipt},
        }
        if expire_by_epoch is not None:
            base["expire_by"] = expire_by_epoch

        with_customer = {
            **base,
            "customer": {"name": customer_name, "contact": _clean_contact(customer_phone)},
        }

        client = self._client()
        import razorpay

        try:
            link = client.payment_link.create(with_customer)
        except razorpay.errors.BadRequestError as exc:
            # Some contacts (e.g. test numbers with recurring digits) fail
            # Razorpay's customer validation. Retry without prefilling the
            # customer — Razorpay collects the details on its hosted page.
            message = str(exc).lower()
            if "contact" in message or "customer" in message:
                logger.warning(
                    "Payment link customer rejected (%s); retrying without prefill", exc
                )
                try:
                    link = client.payment_link.create(base)
                except Exception as exc2:
                    logger.exception("Razorpay payment link creation failed (no customer)")
                    raise PaymentError("Could not create payment link") from exc2
            else:
                logger.exception("Razorpay payment link creation failed")
                raise PaymentError("Could not create payment link") from exc
        except PaymentError:
            raise
        except Exception as exc:
            logger.exception("Razorpay payment link creation failed")
            raise PaymentError("Could not create payment link") from exc
        return PaymentLink(link_id=link["id"], short_url=link["short_url"])

    def verify_webhook(self, body: bytes, signature: str) -> bool:
        if not self._webhook_secret:
            raise PaymentError("Razorpay webhook secret is not configured")
        import razorpay

        try:
            self._client().utility.verify_webhook_signature(
                body.decode("utf-8"), signature, self._webhook_secret
            )
            return True
        except razorpay.errors.SignatureVerificationError:
            return False

    def parse_webhook(self, payload: dict) -> PaymentWebhookEvent:
        event = payload.get("event", "")
        inner = payload.get("payload", {})
        payment_entity = inner.get("payment", {}).get("entity", {})
        link_entity = inner.get("payment_link", {}).get("entity", {})
        order_entity = inner.get("order", {}).get("entity", {})

        payment_id = payment_entity.get("id")
        link_id = link_entity.get("id")
        # hold_id may live on the payment (payment.captured) or on the link/order.
        hold_id = (
            (payment_entity.get("notes") or {}).get("hold_id")
            or (link_entity.get("notes") or {}).get("hold_id")
            or (order_entity.get("notes") or {}).get("hold_id")
        )

        paid_events = {"payment.captured", "payment_link.paid", "order.paid"}
        kind = "paid" if event in paid_events else "other"
        return PaymentWebhookEvent(
            kind=kind, payment_id=payment_id, hold_id=hold_id, link_id=link_id
        )

    def refund_payment(self, payment_id: str, amount: Decimal | None = None) -> str:
        data = {}
        if amount is not None:
            data["amount"] = _to_minor_units(amount)
        try:
            refund = self._client().payment.refund(payment_id, data)
        except PaymentError:
            raise
        except Exception as exc:
            logger.exception("Razorpay refund failed")
            raise PaymentError("Could not process refund") from exc
        return refund["id"]
