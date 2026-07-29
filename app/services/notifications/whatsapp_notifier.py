"""WhatsApp notifier using the Meta WhatsApp Cloud API.

Sends a plain text message via `POST /{phone_number_id}/messages`. All Meta
specifics live here; the booking flow only knows the `Notifier` interface.

IMPORTANT (Meta rules): free-form text can only be delivered inside the 24-hour
customer-service window (i.e. after the user has messaged the business). For
proactive, business-initiated messages (confirmations, payment links) to
arbitrary numbers in production, Meta requires pre-approved message *templates*.
For development/testing with the numbers added to your Meta test app, free-form
text works. Template support can be added here later without touching callers.
"""

import logging

from app.services.notifications.base import Message, NotificationError

logger = logging.getLogger(__name__)


def _to_e164_digits(phone: str, default_country_code: str = "") -> str:
    """Meta expects the number as digits only in full international form.

    A bare local number (e.g. a 10-digit Indian mobile with no country code) is
    prefixed with `default_country_code`; numbers that already include a country
    code (via a leading '+' or being longer than 10 digits) are left as-is.
    """
    already_international = phone.strip().startswith("+")
    digits = "".join(ch for ch in phone if ch.isdigit())
    if not already_international and default_country_code and len(digits) == 10:
        return f"{default_country_code}{digits}"
    return digits


class WhatsAppNotifier:
    name = "whatsapp"

    def __init__(
        self,
        phone_number_id: str,
        access_token: str,
        api_version: str,
        default_country_code: str = "",
    ) -> None:
        self._phone_number_id = phone_number_id
        self._access_token = access_token
        self._api_version = api_version
        self._default_country_code = default_country_code

    def send(self, to_phone: str, message: Message, *, channel: str = "whatsapp") -> None:
        if not self._phone_number_id or not self._access_token:
            raise NotificationError("WhatsApp credentials are not configured")

        import httpx

        recipient = _to_e164_digits(to_phone, self._default_country_code)
        url = f"https://graph.facebook.com/{self._api_version}/{self._phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "text",
            "text": {"preview_url": True, "body": message.text},
        }
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }
        try:
            response = httpx.post(url, json=payload, headers=headers, timeout=15)
        except httpx.HTTPError as exc:
            raise NotificationError(f"WhatsApp request failed: {exc}") from exc

        if response.status_code >= 400:
            # Surface Meta's error body to the logs to make setup issues obvious.
            raise NotificationError(
                f"WhatsApp send failed ({response.status_code}): {response.text}"
            )
        logger.info("WhatsApp message sent to %s", recipient)
