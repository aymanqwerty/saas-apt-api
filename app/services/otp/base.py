"""Provider-agnostic OTP delivery interface.

Patient auth depends only on this interface, never on a concrete SMS gateway.
Switching to a real provider (e.g. Twilio / MSG91) means writing a new class
that satisfies `OtpSender` and pointing the factory at it — no changes to the
auth logic.
"""

from typing import Protocol, runtime_checkable


class OtpError(Exception):
    """Raised when the OTP cannot be delivered (config/network/API)."""


@runtime_checkable
class OtpSender(Protocol):
    """The contract every OTP delivery implementation must satisfy."""

    name: str

    def send(self, phone_number: str, code: str, *, doctor_name: str) -> None:
        """Deliver `code` to `phone_number`. Raise OtpError on failure."""
        ...
