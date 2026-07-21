import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.doctor_settings import DoctorSettings


class SettingsRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_for_doctor(self, doctor_id: uuid.UUID) -> DoctorSettings | None:
        stmt = select(DoctorSettings).where(DoctorSettings.doctor_id == doctor_id)
        return self._db.scalar(stmt)

    def add(self, settings: DoctorSettings) -> None:
        self._db.add(settings)
        self._db.flush()
