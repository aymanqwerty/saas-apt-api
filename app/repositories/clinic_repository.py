import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.clinic import Clinic, ClinicStatus


class ClinicRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def count_active(self, doctor_id: uuid.UUID) -> int:
        return (
            self._db.scalar(
                select(func.count())
                .select_from(Clinic)
                .where(
                    Clinic.doctor_id == doctor_id,
                    Clinic.deleted_at.is_(None),
                    Clinic.status == ClinicStatus.ACTIVE,
                )
            )
            or 0
        )

    def list_for_doctor(
        self,
        doctor_id: uuid.UUID,
        search: str | None = None,
        status: ClinicStatus | None = None,
    ) -> list[Clinic]:
        stmt = select(Clinic).where(
            Clinic.doctor_id == doctor_id,
            Clinic.deleted_at.is_(None),
        )
        if search:
            stmt = stmt.where(Clinic.clinic_name.ilike(f"%{search}%"))
        if status:
            stmt = stmt.where(Clinic.status == status)
        stmt = stmt.order_by(Clinic.created_at.desc())
        return list(self._db.scalars(stmt))

    def get_for_doctor(self, doctor_id: uuid.UUID, clinic_id: uuid.UUID) -> Clinic | None:
        stmt = select(Clinic).where(
            Clinic.id == clinic_id,
            Clinic.doctor_id == doctor_id,
            Clinic.deleted_at.is_(None),
        )
        return self._db.scalar(stmt)

    def add(self, clinic: Clinic) -> None:
        self._db.add(clinic)
        self._db.flush()
