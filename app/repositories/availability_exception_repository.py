import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.availability_exception import AvailabilityException


class AvailabilityExceptionRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_for_doctor(self, doctor_id: uuid.UUID) -> list[AvailabilityException]:
        stmt = (
            select(AvailabilityException)
            .where(AvailabilityException.doctor_id == doctor_id)
            .order_by(AvailabilityException.exception_date.desc())
        )
        return list(self._db.scalars(stmt))

    def get_for_doctor(
        self, doctor_id: uuid.UUID, exception_id: uuid.UUID
    ) -> AvailabilityException | None:
        stmt = select(AvailabilityException).where(
            AvailabilityException.id == exception_id,
            AvailabilityException.doctor_id == doctor_id,
        )
        return self._db.scalar(stmt)

    def find_conflict(
        self,
        doctor_id: uuid.UUID,
        clinic_id: uuid.UUID | None,
        exception_date: date,
        exclude_id: uuid.UUID | None = None,
    ) -> AvailabilityException | None:
        """An exception already exists for this (doctor, clinic, date)."""
        stmt = select(AvailabilityException).where(
            AvailabilityException.doctor_id == doctor_id,
            AvailabilityException.exception_date == exception_date,
        )
        if clinic_id is None:
            stmt = stmt.where(AvailabilityException.clinic_id.is_(None))
        else:
            stmt = stmt.where(AvailabilityException.clinic_id == clinic_id)
        if exclude_id is not None:
            stmt = stmt.where(AvailabilityException.id != exclude_id)
        return self._db.scalar(stmt)

    def list_for_doctor_in_range(
        self, doctor_id: uuid.UUID, start: date, end: date
    ) -> list[AvailabilityException]:
        stmt = select(AvailabilityException).where(
            AvailabilityException.doctor_id == doctor_id,
            AvailabilityException.exception_date >= start,
            AvailabilityException.exception_date <= end,
        )
        return list(self._db.scalars(stmt))

    def add(self, exception: AvailabilityException) -> None:
        self._db.add(exception)
        self._db.flush()

    def delete(self, exception: AvailabilityException) -> None:
        self._db.delete(exception)
        self._db.flush()
