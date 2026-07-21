import uuid
from datetime import date

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.clinic import ClinicStatus
from app.models.doctor import Doctor
from app.models.patient import PatientRelationship
from app.repositories.clinic_repository import ClinicRepository
from app.repositories.patient_repository import PatientRepository
from app.schemas.agent import (
    AgentBookingRequest,
    AgentBookingResult,
    AgentClinic,
    AgentMember,
    AgentPatient,
    AgentPatientLookup,
)
from app.schemas.public import PublicSlot
from app.services.booking_service import BookingService
from app.services.public_service import PublicService
from app.utils.address import compose_clinic_address


class AgentService:
    """Read + orchestration surface exposed to a doctor's voice agent.

    Availability reuses PublicService; booking reuses BookingService. The agent
    never gets its own booking logic — this is a thin, doctor-scoped facade.
    """

    def __init__(self, db: Session) -> None:
        self._db = db
        self._clinics = ClinicRepository(db)
        self._patients = PatientRepository(db)
        self._public = PublicService(db)

    def list_clinics(self, doctor: Doctor) -> list[AgentClinic]:
        clinics = self._clinics.list_for_doctor(doctor.id, status=ClinicStatus.ACTIVE)
        return [
            AgentClinic(
                id=c.id,
                clinic_name=c.clinic_name,
                address=compose_clinic_address(c),
                consultation_fee=c.consultation_fee,
            )
            for c in clinics
        ]

    def available_dates(
        self, doctor: Doctor, clinic_id: uuid.UUID, date_from: date, date_to: date
    ) -> list[date]:
        return self._public.list_available_dates(doctor.slug, clinic_id, date_from, date_to)

    def slots(self, doctor: Doctor, clinic_id: uuid.UUID, slot_date: date) -> list[PublicSlot]:
        return self._public.list_available_slots(doctor.slug, clinic_id, slot_date)

    def lookup_patient(self, doctor: Doctor, phone_number: str) -> AgentPatientLookup:
        patient = self._patients.get_by_phone(doctor.id, phone_number)
        if patient is None:
            return AgentPatientLookup(found=False)

        members: list[AgentMember] = []
        if patient.account_id is not None and patient.relationship == PatientRelationship.SELF:
            members = [
                AgentMember(
                    id=m.id,
                    name=m.full_name,
                    relationship=m.relationship,
                    age=m.age,
                    gender=m.gender,
                )
                for m in self._patients.list_members_for_account(patient.account_id)
            ]

        return AgentPatientLookup(
            found=True,
            patient=AgentPatient(
                name=patient.full_name,
                phone_number=patient.phone_number,
                age=patient.age,
                gender=patient.gender,
                email=patient.email,
            ),
            members=members,
        )

    def book(
        self, doctor: Doctor, data: AgentBookingRequest, request: Request | None = None
    ) -> AgentBookingResult:
        return BookingService(self._db).start_agent_booking(doctor, data, request=request)
