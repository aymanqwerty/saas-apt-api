import logging

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.exceptions import ApiException
from app.core.security import create_access_token, verify_password
from app.models.doctor import Doctor, DoctorStatus
from app.repositories.doctor_repository import DoctorRepository
from app.services.activity_log_service import ActivityLogService

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._doctors = DoctorRepository(db)
        self._activity = ActivityLogService(db)

    def login(
        self, email: str, password: str, request: Request | None = None
    ) -> tuple[str, Doctor]:
        doctor = self._doctors.get_by_email(email)

        if doctor is None or not verify_password(password, doctor.password_hash):
            raise ApiException(401, "Invalid email or password", "UNAUTHORIZED")

        if doctor.status == DoctorStatus.SUSPENDED:
            raise ApiException(403, "This account has been suspended", "FORBIDDEN")

        token = create_access_token(str(doctor.id))
        self._doctors.update_last_login(doctor)
        self._activity.record(doctor.id, "LOGIN", "Doctor", doctor.id, request=request)
        self._db.commit()

        logger.info("Doctor logged in: %s", doctor.id)
        return token, doctor
