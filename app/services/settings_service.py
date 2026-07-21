import uuid

from sqlalchemy.orm import Session

from app.models.doctor_settings import DoctorSettings
from app.repositories.settings_repository import SettingsRepository
from app.schemas.settings import SettingsUpdate


class SettingsService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._settings = SettingsRepository(db)

    def get_or_create(self, doctor_id: uuid.UUID) -> DoctorSettings:
        settings = self._settings.get_for_doctor(doctor_id)
        if settings is None:
            settings = DoctorSettings(doctor_id=doctor_id)
            self._settings.add(settings)
            self._db.commit()
            self._db.refresh(settings)
        return settings

    def update(self, doctor_id: uuid.UUID, data: SettingsUpdate) -> DoctorSettings:
        settings = self.get_or_create(doctor_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(settings, field, value)
        self._db.commit()
        self._db.refresh(settings)
        return settings
