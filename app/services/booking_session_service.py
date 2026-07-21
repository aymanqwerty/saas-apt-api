from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.exceptions import ApiException
from app.models.booking_session import BookingSessionStatus
from app.repositories.booking_session_repository import BookingSessionRepository
from app.repositories.doctor_repository import DoctorRepository
from app.schemas.booking_session import BookingSessionPublic


class BookingSessionService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._sessions = BookingSessionRepository(db)
        self._doctors = DoctorRepository(db)

    def get_public(self, token: str) -> BookingSessionPublic:
        session = self._sessions.get_by_token(token)
        if session is None or session.status != BookingSessionStatus.DRAFT:
            raise ApiException(404, "This booking link is no longer valid", "NOT_FOUND")
        if session.expires_at <= datetime.now(UTC):
            raise ApiException(410, "This booking link has expired", "SESSION_EXPIRED")

        doctor = self._doctors.get_by_id(session.doctor_id)
        if doctor is None:
            raise ApiException(404, "This booking link is no longer valid", "NOT_FOUND")

        return BookingSessionPublic(
            token=session.token,
            doctor_slug=doctor.slug,
            clinic_id=session.clinic_id,
            clinic_name=session.clinic_name,
            slot_id=session.slot_id,
            slot_date=session.slot_date,
            start_time=session.start_time,
            end_time=session.end_time,
            name=session.name,
            phone_number=session.phone_number,
            email=session.email,
            age=session.age,
            gender=session.gender,
            reason=session.reason,
            expires_at=session.expires_at,
        )
