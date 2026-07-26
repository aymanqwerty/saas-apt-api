"""OTP sender that delivers our generated code as an SMS via MSG91.

We keep OTP generation and verification in-house (OtpChallenge); MSG91 is only
the delivery channel. The code is injected into a DLT-approved OTP template
(``##OTP##`` placeholder) via MSG91's OTP send API, passing our own ``otp`` so
MSG91 does not generate its own.

Docs: https://docs.msg91.com/reference/send-otp
"""

import logging

from app.services.otp.base import OtpError

logger = logging.getLogger(__name__)

MSG91_OTP_URL = "https://control.msg91.com/api/v5/otp"


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
    ) -> None:
        self._authkey = authkey
        self._template_id = template_id
        self._sender_id = sender_id
        self._default_country_code = default_country_code

    def send(self, phone_number: str, code: str, *, doctor_name: str) -> None:
        if not self._authkey or not self._template_id:
            raise OtpError("MSG91 is not configured")

        import httpx

        mobile = _to_msg91_mobile(phone_number, self._default_country_code)
        params = {
            "template_id": self._template_id,
            "mobile": mobile,
            "otp": code,  # send OUR generated code; MSG91 fills ##OTP##
        }
        if self._sender_id:
            params["sender"] = self._sender_id
        headers = {"authkey": self._authkey, "accept": "application/json"}

        try:
            response = httpx.post(MSG91_OTP_URL, params=params, headers=headers, timeout=15)
        except httpx.HTTPError as exc:
            raise OtpError(f"MSG91 request failed: {exc}") from exc

        if response.status_code >= 400:
            raise OtpError(f"MSG91 send failed ({response.status_code}): {response.text}")

        # MSG91 returns HTTP 200 even for logical errors — the outcome is in `type`.
        try:
            data = response.json()
        except ValueError:
            data = {}
        if isinstance(data, dict) and str(data.get("type", "")).lower() == "error":
            raise OtpError(f"MSG91 error: {data.get('message') or response.text}")

        request_id = data.get("request_id") if isinstance(data, dict) else None
        logger.info("OTP sent via MSG91 to %s (request_id=%s)", mobile, request_id)
