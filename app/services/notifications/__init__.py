"""Notifier factory — the single switch point for WhatsApp/SMS delivery."""

from app.core.config import settings
from app.services.notifications.base import (
    TEMPLATE_APPOINTMENT_CONFIRMED,
    TEMPLATE_PAYMENT_LINK,
    TEMPLATE_REVIEW_LINK,
    Message,
    NotificationError,
    Notifier,
)
from app.services.notifications.console_notifier import ConsoleNotifier
from app.services.notifications.msg91_whatsapp_notifier import Msg91WhatsAppNotifier
from app.services.notifications.whatsapp_notifier import WhatsAppNotifier

__all__ = [
    "TEMPLATE_APPOINTMENT_CONFIRMED",
    "TEMPLATE_PAYMENT_LINK",
    "TEMPLATE_REVIEW_LINK",
    "ConsoleNotifier",
    "Message",
    "Msg91WhatsAppNotifier",
    "NotificationError",
    "Notifier",
    "WhatsAppNotifier",
    "get_notifier",
]


def get_notifier() -> Notifier:
    provider = settings.notification_provider.lower()
    if provider == "console":
        return ConsoleNotifier()
    if provider == "whatsapp":
        return WhatsAppNotifier(
            settings.whatsapp_phone_number_id,
            settings.whatsapp_access_token,
            settings.whatsapp_api_version,
            settings.whatsapp_default_country_code,
        )
    if provider == "msg91_whatsapp":
        # Fail at construction rather than at the first booking: a misconfigured
        # deploy should be obvious immediately, not silently un-notified.
        missing = [
            name
            for name, value in (
                ("MSG91_WA_AUTHKEY", settings.msg91_wa_authkey),
                ("MSG91_WA_INTEGRATED_NUMBER", settings.msg91_wa_integrated_number),
            )
            if not value
        ]
        if missing:
            raise NotificationError(
                f"NOTIFICATION_PROVIDER=msg91_whatsapp but {', '.join(missing)} is not set"
            )
        return Msg91WhatsAppNotifier(
            settings.msg91_wa_authkey,
            settings.msg91_wa_integrated_number,
            {
                TEMPLATE_APPOINTMENT_CONFIRMED: settings.msg91_wa_template_appointment_confirmed,
                TEMPLATE_PAYMENT_LINK: settings.msg91_wa_template_payment_link,
                TEMPLATE_REVIEW_LINK: settings.msg91_wa_template_review_link,
            },
            settings.msg91_wa_language,
            settings.msg91_wa_namespace,
            settings.msg91_wa_default_country_code,
        )
    raise NotificationError(f"Unknown notification provider: {settings.notification_provider}")
