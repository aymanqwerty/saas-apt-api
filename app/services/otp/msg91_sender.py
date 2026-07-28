"""OTP sender that delivers our generated code as an SMS via MSG91.

We keep OTP generation and verification in-house (OtpChallenge); MSG91 is only
the delivery channel.

**Why the Flow API and not the OTP API.** MSG91 exposes two products. The OTP
API (``/api/v5/otp``) only knows templates registered under its own OTP section
and fills the fixed ``##OTP##`` placeholder. Our DLT template is registered as a
*flow* — addressed by a 24-char ObjectId, with a named ``##var##`` placeholder.
Posting a flow template to the OTP endpoint returns ``type: success`` and then
silently discards the message: nothing is sent and nothing appears in the MSG91
logs. So we post to the flow endpoint, supplying the code as a named variable.

The variable name is configuration (``MSG91_OTP_VARIABLE``), not a constant,
because it is baked into the DLT-approved template and changes whenever that
template is re-registered.

Docs: https://docs.msg91.com/reference/send-sms (flow API)
"""

import logging
from typing import Any

from app.services.otp.base import OtpError

logger = logging.getLogger(__name__)

MSG91_FLOW_URL = "https://control.msg91.com/api/v5/flow/"

# One retry covers a dropped connection or a blip at the gateway. We do not
# retry on a rejection: MSG91 has already made a decision, and a patient is
# waiting on the request.
_MAX_ATTEMPTS = 2
_TIMEOUT_SECONDS = 15.0


def _to_msg91_mobile(phone: str, default_country_code: str) -> str:
    """MSG91 wants digits only in full international form (e.g. 919876543210)."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    if default_country_code and len(digits) == 10:
        return f"{default_country_code}{digits}"
    return digits


class Msg91OtpSender:
    name = "msg91"

    def __init__(
        self,
        authkey: str,
        template_id: str,
        sender_id: str,
        default_country_code: str = "91",
        variable: str = "var",
    ) -> None:
        self._authkey = authkey
        self._template_id = template_id
        self._sender_id = sender_id
        self._default_country_code = default_country_code
        self._variable = variable or "var"

    def send(self, phone_number: str, code: str, *, doctor_name: str) -> None:
        if not self._authkey or not self._template_id:
            raise OtpError("MSG91 is not configured")

        import httpx

        mobile = _to_msg91_mobile(phone_number, self._default_country_code)
        # The code fills the template's named placeholder (##var## by default).
        recipient: dict[str, str] = {"mobiles": mobile, self._variable: code}
        payload: dict[str, Any] = {
            "template_id": self._template_id,
            "short_url": "0",
            "recipients": [recipient],
        }
        if self._sender_id:
            payload["sender"] = self._sender_id
        headers = {
            "authkey": self._authkey,
            "accept": "application/json",
            "content-type": "application/json",
        }

        last_error: Exception | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                response = httpx.post(
                    MSG91_FLOW_URL, json=payload, headers=headers, timeout=_TIMEOUT_SECONDS
                )
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning(
                    "MSG91 request failed (attempt %s/%s): %s", attempt, _MAX_ATTEMPTS, exc
                )
                continue

            self._raise_for_response(response)
            return

        raise OtpError(f"MSG91 request failed: {last_error}") from last_error

    @staticmethod
    def _raise_for_response(response: Any) -> None:
        """Turn a MSG91 reply into either success or an OtpError.

        MSG91 answers HTTP 200 even for logical failures (bad template, unknown
        variable, blocked number) — the real outcome is the `type` field.
        """
        if response.status_code >= 400:
            raise OtpError(f"MSG91 send failed ({response.status_code}): {response.text}")

        try:
            data = response.json()
        except ValueError:
            data = {}

        if isinstance(data, dict) and str(data.get("type", "")).lower() == "error":
            raise OtpError(f"MSG91 error: {data.get('message') or response.text}")

        # The flow API returns the request id under `message`; the OTP API used
        # `request_id`. Accept either so the log line is useful regardless.
        request_id = None
        if isinstance(data, dict):
            request_id = data.get("request_id") or data.get("message")
        # Deliberately never log `code` — an OTP must not reach the logs.
        logger.info("OTP dispatched via MSG91 (request_id=%s)", request_id)
