import uuid
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.phone import normalize_phone
from app.models.appointment import Appointment
from app.models.patient import Patient, PatientRelationship


class PatientRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def count_for_doctor(self, doctor_id: uuid.UUID) -> int:
        return (
            self._db.scalar(
                select(func.count()).select_from(Patient).where(Patient.doctor_id == doctor_id)
            )
            or 0
        )

    def get_for_doctor(self, doctor_id: uuid.UUID, patient_id: uuid.UUID) -> Patient | None:
        stmt = select(Patient).where(
            Patient.id == patient_id,
            Patient.doctor_id == doctor_id,
        )
        return self._db.scalar(stmt)

    def stats_for_patient(self, patient_id: uuid.UUID) -> tuple[int, date | None]:
        row = self._db.execute(
            select(
                func.count(Appointment.id),
                func.max(Appointment.appointment_date),
            ).where(Appointment.patient_id == patient_id)
        ).one()
        return int(row[0] or 0), row[1]

    def list_for_doctor(
        self,
        doctor_id: uuid.UUID,
        *,
        search: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[tuple[Patient, int, date | None]], int]:
        filters = [Patient.doctor_id == doctor_id]
        if search:
            like = f"%{search}%"
            filters.append(or_(Patient.full_name.ilike(like), Patient.phone_number.ilike(like)))

        total = self._db.scalar(select(func.count()).select_from(Patient).where(*filters))

        stmt = (
            select(
                Patient,
                func.count(Appointment.id),
                func.max(Appointment.appointment_date),
            )
            .outerjoin(Appointment, Appointment.patient_id == Patient.id)
            .where(*filters)
            .group_by(Patient.id)
            .order_by(Patient.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        rows = [(row[0], int(row[1] or 0), row[2]) for row in self._db.execute(stmt).all()]
        return rows, total or 0

    def get_by_phone(self, doctor_id: uuid.UUID, phone_number: str) -> Patient | None:
        """Return the *primary* patient for a phone (guest record or account holder).

        Family members share the account holder's phone but are never primary,
        so guest bookings always resolve to the single primary record. The phone
        is canonicalised so a lookup matches regardless of how it was typed.
        """
        stmt = select(Patient).where(
            Patient.doctor_id == doctor_id,
            Patient.phone_number == normalize_phone(phone_number),
            or_(
                Patient.relationship.is_(None),
                Patient.relationship == PatientRelationship.SELF,
            ),
        )
        return self._db.scalar(stmt)

    def get_self_for_account(self, account_id: uuid.UUID) -> Patient | None:
        stmt = select(Patient).where(
            Patient.account_id == account_id,
            Patient.relationship == PatientRelationship.SELF,
        )
        return self._db.scalar(stmt)

    def get_for_account(self, account_id: uuid.UUID, patient_id: uuid.UUID) -> Patient | None:
        """A single patient (self or family member) belonging to an account."""
        stmt = select(Patient).where(
            Patient.id == patient_id,
            Patient.account_id == account_id,
        )
        return self._db.scalar(stmt)

    def list_members_for_account(self, account_id: uuid.UUID) -> list[Patient]:
        """Family members (everyone on the account except the SELF record)."""
        stmt = (
            select(Patient)
            .where(
                Patient.account_id == account_id,
                Patient.relationship != PatientRelationship.SELF,
            )
            .order_by(Patient.created_at.asc())
        )
        return list(self._db.scalars(stmt))

    def has_appointments(self, patient_id: uuid.UUID) -> bool:
        stmt = select(Appointment.id).where(Appointment.patient_id == patient_id).limit(1)
        return self._db.scalar(stmt) is not None

    def next_patient_code(self, doctor_id: uuid.UUID) -> str:
        count = self._db.scalar(
            select(func.count()).select_from(Patient).where(Patient.doctor_id == doctor_id)
        )
        return f"P-{(count or 0) + 1:04d}"

    def add(self, patient: Patient) -> None:
        self._db.add(patient)
        self._db.flush()

    def delete(self, patient: Patient) -> None:
        self._db.delete(patient)
        self._db.flush()
