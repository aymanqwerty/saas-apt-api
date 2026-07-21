import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.booking_session import BookingSession


class BookingSessionRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_token(self, token: str) -> BookingSession | None:
        return self._db.scalar(select(BookingSession).where(BookingSession.token == token))

    def get(self, session_id: uuid.UUID) -> BookingSession | None:
        return self._db.scalar(select(BookingSession).where(BookingSession.id == session_id))

    def add(self, session: BookingSession) -> None:
        self._db.add(session)
        self._db.flush()
