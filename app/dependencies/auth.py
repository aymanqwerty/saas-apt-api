import uuid
from typing import Annotated

from fastapi import Depends, Request

from app.core.config import settings
from app.core.exceptions import ApiException
from app.core.security import decode_access_token
from app.dependencies.database import DbSession
from app.models.doctor import Doctor, DoctorStatus
from app.repositories.doctor_repository import DoctorRepository


def _extract_token(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.removeprefix("Bearer ").strip()
    return request.cookies.get(settings.auth_cookie_name)


def get_current_doctor(request: Request, db: DbSession) -> Doctor:
    token = _extract_token(request)
    if not token:
        raise ApiException(401, "Not authenticated", "UNAUTHORIZED")

    subject = decode_access_token(token)
    if subject is None:
        raise ApiException(401, "Invalid or expired token", "UNAUTHORIZED")

    try:
        doctor_id = uuid.UUID(subject)
    except ValueError:
        raise ApiException(401, "Invalid or expired token", "UNAUTHORIZED") from None

    doctor = DoctorRepository(db).get_by_id(doctor_id)
    if doctor is None:
        raise ApiException(401, "Not authenticated", "UNAUTHORIZED")

    if doctor.status == DoctorStatus.SUSPENDED:
        raise ApiException(403, "This account has been suspended", "FORBIDDEN")

    return doctor


CurrentDoctor = Annotated[Doctor, Depends(get_current_doctor)]
