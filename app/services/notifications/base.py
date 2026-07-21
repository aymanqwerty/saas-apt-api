"""Provider-agnostic notification (WhatsApp/SMS) interface.

Booking flows depend only on this interface, never on a concrete provider.
Switching to a real provider (Twilio / Gupshup / MSG91 / WhatsApp Cloud API)
means writing a class that satisfies `Notifier` and pointing the factory at it.
"""

from typing import Protocol, runtime_checkable


class NotificationError(Exception):
    """Raised when a message cannot be delivered."""


@runtime_checkable
class Notifier(Protocol):
    name: str

    def send(self, to_phone: str, message: str, *, channel: str = "whatsapp") -> None:
        """Deliver `message` to `to_phone` over the given channel."""
        ...
