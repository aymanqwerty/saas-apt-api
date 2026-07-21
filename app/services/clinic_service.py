import uuid
from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.exceptions import ApiException
from app.models.clinic import Clinic, ClinicStatus
from app.repositories.clinic_repository import ClinicRepository
from app.schemas.clinic import ClinicCreate, ClinicUpdate
from app.services.activity_log_service import ActivityLogService


class ClinicService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._clinics = ClinicRepository(db)
        self._activity = ActivityLogService(db)

    def list_clinics(
        self,
        doctor_id: uuid.UUID,
        search: str | None = None,
        status: ClinicStatus | None = None,
    ) -> list[Clinic]:
        return self._clinics.list_for_doctor(doctor_id, search=search, status=status)

    def get_clinic(self, doctor_id: uuid.UUID, clinic_id: uuid.UUID) -> Clinic:
        clinic = self._clinics.get_for_doctor(doctor_id, clinic_id)
        if clinic is None:
            raise ApiException(404, "Clinic not found", "NOT_FOUND")
        return clinic

    def create_clinic(
        self, doctor_id: uuid.UUID, data: ClinicCreate, request: Request | None = None
    ) -> Clinic:
        clinic = Clinic(doctor_id=doctor_id, **data.model_dump())
        self._clinics.add(clinic)
        self._activity.record(doctor_id, "CREATE_CLINIC", "Clinic", clinic.id, request=request)
        self._db.commit()
        self._db.refresh(clinic)
        return clinic

    def update_clinic(
        self,
        doctor_id: uuid.UUID,
        clinic_id: uuid.UUID,
        data: ClinicUpdate,
        request: Request | None = None,
    ) -> Clinic:
        clinic = self.get_clinic(doctor_id, clinic_id)

        updates = data.model_dump(exclude_unset=True)
        non_nullable = {
            "clinic_name",
            "address_line_1",
            "city",
            "state",
            "country",
            "timezone",
            "status",
        }
        for field in non_nullable & updates.keys():
            if updates[field] is None:
                raise ApiException(422, f"{field} cannot be empty", "VALIDATION_ERROR")

        for field, value in updates.items():
            setattr(clinic, field, value)

        self._activity.record(doctor_id, "UPDATE_CLINIC", "Clinic", clinic.id, request=request)
        self._db.commit()
        self._db.refresh(clinic)
        return clinic

    def delete_clinic(
        self, doctor_id: uuid.UUID, clinic_id: uuid.UUID, request: Request | None = None
    ) -> None:
        clinic = self.get_clinic(doctor_id, clinic_id)

        # Business rule (docs/03 §4): clinics with future appointments cannot be
        # deleted. The appointments module lands in Milestone 6; this guard is
        # enforced there once appointments exist.

        clinic.deleted_at = datetime.now(UTC)
        self._activity.record(doctor_id, "DELETE_CLINIC", "Clinic", clinic.id, request=request)
        self._db.commit()
