import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import ApiException
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.patient_repository import PatientRepository
from app.schemas.patient import PatientDetail, PatientListItem


class PatientService:
    def __init__(self, db: Session) -> None:
        self._patients = PatientRepository(db)
        self._appointments = AppointmentRepository(db)

    def list_patients(
        self, doctor_id: uuid.UUID, search: str | None, page: int, limit: int
    ) -> tuple[list[PatientListItem], int]:
        rows, total = self._patients.list_for_doctor(
            doctor_id, search=search, page=page, limit=limit
        )
        items = [
            PatientListItem(
                id=patient.id,
                patient_code=patient.patient_code,
                full_name=patient.full_name,
                phone_number=patient.phone_number,
                email=patient.email,
                total_appointments=count,
                last_visit=last_visit,
            )
            for patient, count, last_visit in rows
        ]
        return items, total

    def _require_patient(self, doctor_id: uuid.UUID, patient_id: uuid.UUID) -> Patient:
        patient = self._patients.get_for_doctor(doctor_id, patient_id)
        if patient is None:
            raise ApiException(404, "Patient not found", "NOT_FOUND")
        return patient

    def get_patient(self, doctor_id: uuid.UUID, patient_id: uuid.UUID) -> PatientDetail:
        patient = self._require_patient(doctor_id, patient_id)
        total, last_visit = self._patients.stats_for_patient(patient.id)
        return PatientDetail(
            id=patient.id,
            patient_code=patient.patient_code,
            full_name=patient.full_name,
            phone_number=patient.phone_number,
            email=patient.email,
            age=patient.age,
            gender=patient.gender,
            notes=patient.notes,
            total_appointments=total,
            last_visit=last_visit,
            created_at=patient.created_at,
        )

    def list_patient_appointments(
        self, doctor_id: uuid.UUID, patient_id: uuid.UUID
    ) -> list[Appointment]:
        self._require_patient(doctor_id, patient_id)
        return self._appointments.list_for_patient(doctor_id, patient_id)
