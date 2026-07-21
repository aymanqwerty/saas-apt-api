"""Mints a WebRTC conversation token for a doctor's ElevenLabs voice agent.

Keeps the ElevenLabs API key server-side. The website requests a short-lived
token per conversation so it can connect even to a PRIVATE agent, without ever
exposing the API key or (optionally) the agent id to the browser.
"""

import logging

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ApiException
from app.models.doctor import DoctorStatus
from app.repositories.doctor_repository import DoctorRepository

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://api.elevenlabs.io/v1/convai/conversation/token"


class VoiceTokenService:
    def __init__(self, db: Session) -> None:
        self._doctors = DoctorRepository(db)

    def webrtc_token(self, doctor_slug: str) -> str:
        doctor = self._doctors.get_by_slug(doctor_slug)
        if doctor is None or doctor.status != DoctorStatus.ACTIVE:
            raise ApiException(404, "Doctor not found", "NOT_FOUND")
        if not doctor.elevenlabs_agent_id:
            raise ApiException(404, "Voice assistant is not set up", "AGENT_NOT_CONFIGURED")
        if not settings.elevenlabs_api_key:
            raise ApiException(503, "Voice service is not configured", "VOICE_UNAVAILABLE")

        import httpx

        try:
            response = httpx.get(
                _TOKEN_URL,
                params={"agent_id": doctor.elevenlabs_agent_id},
                headers={"xi-api-key": settings.elevenlabs_api_key},
                timeout=15,
            )
        except httpx.HTTPError as exc:
            logger.exception("ElevenLabs token request failed")
            raise ApiException(502, "Could not start the voice assistant", "VOICE_ERROR") from exc

        if response.status_code >= 400:
            logger.error("ElevenLabs token error %s: %s", response.status_code, response.text)
            raise ApiException(502, "Could not start the voice assistant", "VOICE_ERROR")

        token = response.json().get("token")
        if not token:
            raise ApiException(502, "Could not start the voice assistant", "VOICE_ERROR")
        return token
