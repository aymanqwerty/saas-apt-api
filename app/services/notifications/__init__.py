"""Notifier factory — the single switch point for WhatsApp/SMS delivery."""

from app.core.config import settings
from app.services.notifications.base import NotificationError, Notifier
from app.services.notifications.console_notifier import ConsoleNotifier
from app.services.notifications.whatsapp_notifier import WhatsAppNotifier

__all__ = [
    "ConsoleNotifier",
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
    raise NotificationError(f"Unknown notification provider: {settings.notification_provider}")
