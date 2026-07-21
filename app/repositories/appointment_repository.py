import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment, AppointmentStatus
from app.models.patient import Patient


class AppointmentRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_for_doctor(self, doctor_id: uuid.UUID, appointment_id: uuid.UUID) -> Appointment | None:
        stmt = select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.doctor_id == doctor_id,
        )
        return self._db.scalar(stmt)

    def list_for_doctor(
        self,
        doctor_id: uuid.UUID,
        *,
        status: AppointmentStatus | None = None,
        clinic_id: uuid.UUID | None = None,
        appointment_date: date | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        patient_name: str | None = None,
        appointment_number: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[Appointment], int]:
        filters = [Appointment.doctor_id == doctor_id]
        if status:
            filters.append(Appointment.appointment_status == status)
        if clinic_id:
            filters.append(Appointment.clinic_id == clinic_id)
        if appointment_date:
            filters.append(Appointment.appointment_date == appointment_date)
        if date_from:
            filters.append(Appointment.appointment_date >= date_from)
        if date_to:
            filters.append(Appointment.appointment_date <= date_to)
        if appointment_number:
            filters.append(Appointment.appointment_number.ilike(f"%{appointment_number}%"))
        if patient_name:
            filters.append(Patient.full_name.ilike(f"%{patient_name}%"))

        base = (
            select(Appointment).join(Patient, Appointment.patient_id == Patient.id).where(*filters)
        )

        total = self._db.scalar(select(func.count()).select_from(base.subquery()))

        items = list(
            self._db.scalars(
                base.order_by(Appointment.appointment_date.asc(), Appointment.start_time.asc())
                .offset((page - 1) * limit)
                .limit(limit)
            )
        )
        return items, total or 0

    def list_on_date(self, doctor_id: uuid.UUID, on_date: date) -> list[Appointment]:
        stmt = (
            select(Appointment)
            .where(
                Appointment.doctor_id == doctor_id,
                Appointment.appointment_date == on_date,
                Appointment.appointment_status != AppointmentStatus.CANCELLED,
            )
            .order_by(Appointment.start_time)
        )
        return list(self._db.scalars(stmt))

    def count_upcoming(self, doctor_id: uuid.UUID, after_date: date) -> int:
        return (
            self._db.scalar(
                select(func.count())
                .select_from(Appointment)
                .where(
                    Appointment.doctor_id == doctor_id,
                    Appointment.appointment_date > after_date,
                    Appointment.appointment_status.in_(
                        [AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]
                    ),
                )
            )
            or 0
        )

    def list_for_account(self, account_id: uuid.UUID) -> list[Appointment]:
        """Every appointment booked for any patient (self or family) on an account."""
        stmt = (
            select(Appointment)
            .join(Patient, Appointment.patient_id == Patient.id)
            .where(Patient.account_id == account_id)
            .order_by(Appointment.appointment_date.asc(), Appointment.start_time.asc())
        )
        return list(self._db.scalars(stmt))

    def list_for_patient(self, doctor_id: uuid.UUID, patient_id: uuid.UUID) -> list[Appointment]:
        stmt = (
            select(Appointment)
            .where(
                Appointment.doctor_id == doctor_id,
                Appointment.patient_id == patient_id,
            )
            .order_by(Appointment.appointment_date.asc(), Appointment.start_time.asc())
        )
        return list(self._db.scalars(stmt))

    def exists_number(self, appointment_number: str) -> bool:
        stmt = select(Appointment.id).where(Appointment.appointment_number == appointment_number)
        return self._db.scalar(stmt) is not None

    def has_active_for_slot_patient(self, slot_id: uuid.UUID, patient_id: uuid.UUID) -> bool:
        stmt = select(Appointment.id).where(
            Appointment.slot_id == slot_id,
            Appointment.patient_id == patient_id,
            Appointment.appointment_status != "CANCELLED",
        )
        return self._db.scalar(stmt) is not None

    def next_token_number(self, clinic_id: uuid.UUID, appointment_date: date) -> int:
        current_max = self._db.scalar(
            select(func.max(Appointment.token_number)).where(
                Appointment.clinic_id == clinic_id,
                Appointment.appointment_date == appointment_date,
            )
        )
        return (current_max or 0) + 1

    def add(self, appointment: Appointment) -> None:
        self._db.add(appointment)
        self._db.flush()
