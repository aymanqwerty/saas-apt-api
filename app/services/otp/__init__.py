"""OTP sender factory — the single switch point for SMS delivery.

To change providers, add an implementation of `OtpSender` and return it here
based on `settings.otp_provider`. Nothing else in the app references a concrete
sender.
"""

from app.core.config import settings
from app.services.otp.base import OtpError, OtpSender
from app.services.otp.console_sender import ConsoleOtpSender

__all__ = [
    "ConsoleOtpSender",
    "OtpError",
    "OtpSender",
    "get_otp_sender",
]


def get_otp_sender() -> OtpSender:
    provider = settings.otp_provider.lower()
    if provider == "console":
        return ConsoleOtpSender()
    raise OtpError(f"Unknown OTP provider: {settings.otp_provider}")
