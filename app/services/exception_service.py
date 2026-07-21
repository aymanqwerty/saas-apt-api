import uuid

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.exceptions import ApiException
from app.models.availability_exception import AvailabilityException
from app.repositories.availability_exception_repository import (
    AvailabilityExceptionRepository,
)
from app.repositories.clinic_repository import ClinicRepository
from app.schemas.availability_exception import (
    AvailabilityExceptionCreate,
    AvailabilityExceptionUpdate,
)
from app.services.activity_log_service import ActivityLogService
from app.services.slot_generation_service import SlotGenerationService


class ExceptionService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._exceptions = AvailabilityExceptionRepository(db)
        self._clinics = ClinicRepository(db)
        self._activity = ActivityLogService(db)
        self._generation = SlotGenerationService(db)

    def list_exceptions(self, doctor_id: uuid.UUID) -> list[AvailabilityException]:
        return self._exceptions.list_for_doctor(doctor_id)

    def _validate_clinic(self, doctor_id: uuid.UUID, clinic_id: uuid.UUID | None) -> None:
        if clinic_id is not None and self._clinics.get_for_doctor(doctor_id, clinic_id) is None:
            raise ApiException(404, "Clinic not found", "NOT_FOUND")

    def create_exception(
        self,
        doctor_id: uuid.UUID,
        data: AvailabilityExceptionCreate,
        request: Request | None = None,
    ) -> AvailabilityException:
        self._validate_clinic(doctor_id, data.clinic_id)

        if self._exceptions.find_conflict(doctor_id, data.clinic_id, data.exception_date):
            raise ApiException(409, "An exception already exists for this date", "CONFLICT")

        exception = AvailabilityException(doctor_id=doctor_id, **data.model_dump())
        self._exceptions.add(exception)
        self._generation.rebuild_doctor_date(
            doctor_id, exception.exception_date, exception.clinic_id
        )
        self._activity.record(
            doctor_id, "CREATE_EXCEPTION", "AvailabilityException", exception.id, request=request
        )
        self._db.commit()
        self._db.refresh(exception)
        return exception

    def update_exception(
        self,
        doctor_id: uuid.UUID,
        exception_id: uuid.UUID,
        data: AvailabilityExceptionUpdate,
        request: Request | None = None,
    ) -> AvailabilityException:
        exception = self._exceptions.get_for_doctor(doctor_id, exception_id)
        if exception is None:
            raise ApiException(404, "Exception not found", "NOT_FOUND")

        old_date = exception.exception_date
        old_clinic_id = exception.clinic_id

        updates = data.model_dump(exclude_unset=True)
        if "clinic_id" in updates:
            self._validate_clinic(doctor_id, updates["clinic_id"])
        for field, value in updates.items():
            setattr(exception, field, value)

        conflict = self._exceptions.find_conflict(
            doctor_id, exception.clinic_id, exception.exception_date, exclude_id=exception.id
        )
        if conflict is not None:
            raise ApiException(409, "An exception already exists for this date", "CONFLICT")

        # Rebuild the previously affected date and the newly affected date.
        self._generation.rebuild_doctor_date(doctor_id, old_date, old_clinic_id)
        self._generation.rebuild_doctor_date(
            doctor_id, exception.exception_date, exception.clinic_id
        )
        self._activity.record(
            doctor_id, "UPDATE_EXCEPTION", "AvailabilityException", exception.id, request=request
        )
        self._db.commit()
        self._db.refresh(exception)
        return exception

    def delete_exception(
        self, doctor_id: uuid.UUID, exception_id: uuid.UUID, request: Request | None = None
    ) -> None:
        exception = self._exceptions.get_for_doctor(doctor_id, exception_id)
        if exception is None:
            raise ApiException(404, "Exception not found", "NOT_FOUND")

        affected_date = exception.exception_date
        affected_clinic = exception.clinic_id
        exception_id_value = exception.id

        self._exceptions.delete(exception)
        self._generation.rebuild_doctor_date(doctor_id, affected_date, affected_clinic)
        self._activity.record(
            doctor_id,
            "DELETE_EXCEPTION",
            "AvailabilityException",
            exception_id_value,
            request=request,
        )
        self._db.commit()
