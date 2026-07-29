"""WhatsApp notifier using MSG91's WhatsApp (WABA) API.

Unlike the Meta free-form notifier, this sends **pre-approved templates**, which
is the only way to reach a patient outside the 24-hour customer-service window —
i.e. the only way booking confirmations and payment links actually arrive.

We supply values, not wording: `Message.template` is our logical key, mapped
here onto the approved template name, and `Message.variables` fill the template's
positional `{{1}}..{{n}}` placeholders in order. The copy itself lives in the
MSG91/Meta template and cannot be changed from code without re-approval.

NOTE: this uses a DIFFERENT MSG91 account from the SMS/OTP sender, so it has its
own authkey (`MSG91_WA_AUTHKEY`) — do not collapse the two.

Docs: https://docs.msg91.com/whatsapp
"""

import logging
from typing import Any

from app.services.notifications.base import Message, NotificationError

logger = logging.getLogger(__name__)

MSG91_WA_URL = "https://control.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/bulk/"

_TIMEOUT_SECONDS = 15.0


def _to_wa_digits(phone: str, default_country_code: str = "") -> str:
    """MSG91 wants digits only in full international form (e.g. 919876543210)."""
    already_international = phone.strip().startswith("+")
    digits = "".join(ch for ch in phone if ch.isdigit())
    if not already_international and default_country_code and len(digits) == 10:
        return f"{default_country_code}{digits}"
    return digits


class Msg91WhatsAppNotifier:
    name = "msg91_whatsapp"

    def __init__(
        self,
        authkey: str,
        integrated_number: str,
        templates: dict[str, str],
        language: str = "en",
        namespace: str = "",
        default_country_code: str = "91",
    ) -> None:
        self._authkey = authkey
        self._integrated_number = integrated_number
        self._templates = templates
        self._language = language
        self._namespace = namespace
        self._default_country_code = default_country_code

    def send(self, to_phone: str, message: Message, *, channel: str = "whatsapp") -> None:
        if not self._authkey or not self._integrated_number:
            raise NotificationError("MSG91 WhatsApp credentials are not configured")

        template_name = self._templates.get(message.template)
        if not template_name:
            raise NotificationError(
                f"No MSG91 WhatsApp template configured for '{message.template}'"
            )

        import httpx

        recipient = _to_wa_digits(to_phone, self._default_country_code)
        # Positional variables fill body_1..body_n, in the order the caller built
        # them — this must match the approved template's {{1}}..{{n}}.
        components = {
            f"body_{index}": {"type": "text", "value": value}
            for index, value in enumerate(message.variables, start=1)
        }

        template: dict[str, Any] = {
            "name": template_name,
            "language": {"code": self._language, "policy": "deterministic"},
            "to_and_components": [{"to": [recipient], "components": components}],
        }
        if self._namespace:
            template["namespace"] = self._namespace

        payload = {
            "integrated_number": self._integrated_number,
            "content_type": "template",
            "payload": {
                "messaging_product": "whatsapp",
                "type": "template",
                "template": template,
            },
        }
        headers = {
            "authkey": self._authkey,
            "accept": "application/json",
            "content-type": "application/json",
        }

        try:
            response = httpx.post(
                MSG91_WA_URL, json=payload, headers=headers, timeout=_TIMEOUT_SECONDS
            )
        except httpx.HTTPError as exc:
            raise NotificationError(f"MSG91 WhatsApp request failed: {exc}") from exc

        if response.status_code >= 400:
            raise NotificationError(
                f"MSG91 WhatsApp send failed ({response.status_code}): {response.text}"
            )

        # Like the SMS API, MSG91 answers HTTP 200 for logical failures too —
        # an unapproved template or bad variable count shows up in `type`.
        try:
            data = response.json()
        except ValueError:
            data = {}
        if isinstance(data, dict) and str(data.get("type", "")).lower() == "error":
            raise NotificationError(f"MSG91 WhatsApp error: {data.get('message') or response.text}")

        request_id = None
        if isinstance(data, dict):
            request_id = data.get("request_id") or data.get("message")
        logger.info(
            "WhatsApp template '%s' sent to %s via MSG91 (request_id=%s)",
            template_name,
            recipient,
            request_id,
        )
