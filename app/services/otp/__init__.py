"""OTP sender factory — the single switch point for SMS delivery.

To change providers, add an implementation of `OtpSender` and return it here
based on `settings.otp_provider`. Nothing else in the app references a concrete
sender.
"""

from app.core.config import settings
from app.services.otp.base import OtpError, OtpSender
from app.services.otp.console_sender import ConsoleOtpSender
from app.services.otp.msg91_sender import Msg91OtpSender

__all__ = [
    "ConsoleOtpSender",
    "Msg91OtpSender",
    "OtpError",
    "OtpSender",
    "get_otp_sender",
]


def get_otp_sender() -> OtpSender:
    provider = settings.otp_provider.lower()
    if provider == "console":
        return ConsoleOtpSender()
    if provider == "msg91":
        # Fail loudly at construction rather than at the first patient login:
        # a misconfigured production deploy should be obvious immediately.
        missing = [
            name
            for name, value in (
                ("MSG91_AUTHKEY", settings.msg91_authkey),
                ("MSG91_OTP_TEMPLATE_ID", settings.msg91_otp_template_id),
            )
            if not value
        ]
        if missing:
            raise OtpError(f"OTP_PROVIDER=msg91 but {', '.join(missing)} is not set")
        return Msg91OtpSender(
            settings.msg91_authkey,
            settings.msg91_otp_template_id,
            settings.msg91_sender_id,
            settings.msg91_default_country_code,
            settings.msg91_otp_variable,
        )
    raise OtpError(f"Unknown OTP provider: {settings.otp_provider}")
