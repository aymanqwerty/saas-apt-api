import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.doctor import Doctor


class DoctorRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_email(self, email: str) -> Doctor | None:
        stmt = select(Doctor).where(
            Doctor.email == email,
            Doctor.deleted_at.is_(None),
        )
        return self._db.scalar(stmt)

    def get_by_id(self, doctor_id: uuid.UUID) -> Doctor | None:
        stmt = select(Doctor).where(
            Doctor.id == doctor_id,
            Doctor.deleted_at.is_(None),
        )
        return self._db.scalar(stmt)

    def get_by_slug(self, slug: str) -> Doctor | None:
        stmt = select(Doctor).where(
            Doctor.slug == slug,
            Doctor.deleted_at.is_(None),
        )
        return self._db.scalar(stmt)

    def get_by_agent_key(self, agent_api_key: str) -> Doctor | None:
        stmt = select(Doctor).where(
            Doctor.agent_api_key == agent_api_key,
            Doctor.deleted_at.is_(None),
        )
        return self._db.scalar(stmt)

    def update_last_login(self, doctor: Doctor) -> None:
        doctor.last_login = datetime.now(UTC)
        self._db.flush()
