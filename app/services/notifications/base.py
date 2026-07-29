"""Provider-agnostic notification (WhatsApp/SMS) interface.

Booking flows depend only on this interface, never on a concrete provider.
Switching to a real provider (Twilio / Gupshup / MSG91 / WhatsApp Cloud API)
means writing a class that satisfies `Notifier` and pointing the factory at it.

A notification is carried as a `Message`, which holds BOTH renderings:

* `text`     — the fully composed free-form body. Console logs it; Meta's Cloud
               API sends it verbatim (valid only inside the 24-hour window).
* `template` + `variables` — what a template-only channel needs. Business-
               initiated WhatsApp requires a pre-approved template, so the
               wording lives with the provider and we supply the values.

Callers build both once; each provider uses whichever it supports. That keeps
the free-form providers working unchanged while templated ones become possible.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# Logical template keys. These are OUR names for the three messages we send;
# each provider maps them onto whatever the gateway calls them.
TEMPLATE_APPOINTMENT_CONFIRMED = "appointment_confirmed"
TEMPLATE_PAYMENT_LINK = "payment_link"
TEMPLATE_REVIEW_LINK = "review_link"


class NotificationError(Exception):
    """Raised when a message cannot be delivered."""


@dataclass(frozen=True)
class Message:
    """One notification, renderable as free-form text or as a template call."""

    template: str
    variables: tuple[str, ...]
    text: str


@runtime_checkable
class Notifier(Protocol):
    name: str

    def send(self, to_phone: str, message: Message, *, channel: str = "whatsapp") -> None:
        """Deliver `message` to `to_phone` over the given channel."""
        ...
