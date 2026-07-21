"""Provider-agnostic payment gateway interface.

The booking flow depends only on this interface, never on a concrete gateway.
Switching providers (e.g. Razorpay -> Stripe) means writing a new class that
satisfies `PaymentProvider` and pointing the factory at it — no changes to the
booking or admin logic.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable


class PaymentError(Exception):
    """Raised when the gateway cannot complete an operation (config/network/API)."""


@dataclass(frozen=True)
class PaymentOrder:
    """A gateway order the client uses to start checkout."""

    order_id: str
    amount: int  # smallest currency unit (e.g. paise for INR)
    currency: str


@dataclass(frozen=True)
class PaymentLink:
    """A hosted payment link that can be sent over WhatsApp/SMS."""

    link_id: str
    short_url: str


@dataclass(frozen=True)
class PaymentWebhookEvent:
    """Normalised webhook event so the endpoint stays provider-neutral."""

    kind: str  # "paid" for a successful payment; "other" otherwise
    payment_id: str | None
    # Correlators — whichever the provider can supply. `hold_id` comes from the
    # payment/link notes we set at creation; `link_id` from payment_link events.
    hold_id: str | None = None
    link_id: str | None = None


@runtime_checkable
class PaymentProvider(Protocol):
    """The contract every payment gateway implementation must satisfy."""

    name: str

    def create_order(self, amount: Decimal, currency: str, receipt: str) -> PaymentOrder:
        """Create a gateway order for `amount` (major units) and return it."""
        ...

    def verify_payment(self, order_id: str, payment_id: str, signature: str) -> bool:
        """Return True only if the signature proves the payment is authentic."""
        ...

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
        """Create a hosted payment link for `amount` (major units)."""
        ...

    def verify_webhook(self, body: bytes, signature: str) -> bool:
        """Return True only if the webhook signature is authentic."""
        ...

    def parse_webhook(self, payload: dict) -> PaymentWebhookEvent:
        """Normalise a webhook payload into a PaymentWebhookEvent."""
        ...

    def refund_payment(self, payment_id: str, amount: Decimal | None = None) -> str:
        """Refund a captured payment (full if amount is None); return refund id."""
        ...
