from typing import Annotated

from fastapi import Depends, Request

from app.core.exceptions import ApiException
from app.dependencies.database import DbSession
from app.models.doctor import Doctor, DoctorStatus
from app.repositories.doctor_repository import DoctorRepository


def get_agent_doctor(request: Request, db: DbSession) -> Doctor:
    """Resolve the doctor a voice-agent tool call belongs to, via its API key.

    The agent presents a per-doctor secret in the `X-Agent-Key` header (or a
    Bearer token). Every agent endpoint is scoped to the resolved doctor.
    """
    key = request.headers.get("X-Agent-Key")
    if not key:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            key = auth.removeprefix("Bearer ").strip()

    if not key:
        raise ApiException(401, "Missing agent credentials", "UNAUTHORIZED")

    doctor = DoctorRepository(db).get_by_agent_key(key)
    if doctor is None:
        raise ApiException(401, "Invalid agent credentials", "UNAUTHORIZED")
    if doctor.status == DoctorStatus.SUSPENDED:
        raise ApiException(403, "This account is suspended", "FORBIDDEN")

    return doctor


AgentDoctor = Annotated[Doctor, Depends(get_agent_doctor)]
