import uuid
from datetime import date, datetime, time
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.appointment import Appointment, AppointmentStatus


class AppointmentListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    appointment_number: str
    token_number: int
    appointment_status: AppointmentStatus
    clinic_id: uuid.UUID
    clinic_name: str
    appointment_date: date
    start_time: time
    end_time: time
    patient_name: str
    patient_phone: str

    @classmethod
    def from_model(cls, appointment: Appointment) -> "AppointmentListItem":
        return cls(
            id=appointment.id,
            appointment_number=appointment.appointment_number,
            token_number=appointment.token_number,
            appointment_status=appointment.appointment_status,
            clinic_id=appointment.clinic_id,
            clinic_name=appointment.clinic_name,
            appointment_date=appointment.appointment_date,
            start_time=appointment.start_time,
            end_time=appointment.end_time,
            patient_name=appointment.patient.full_name,
            patient_phone=appointment.patient.phone_number,
        )


class AppointmentDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    appointment_number: str
    token_number: int
    appointment_status: AppointmentStatus
    booking_source: str
    clinic_id: uuid.UUID
    clinic_name: str
    clinic_address: str
    doctor_name: str
    consultation_fee: Decimal | None
    appointment_date: date
    start_time: time
    end_time: time
    visit_reason: str | None
    doctor_notes: str | None
    patient_notes: str | None
    cancellation_reason: str | None
    patient_id: uuid.UUID
    patient_name: str
    patient_phone: str
    patient_email: str | None
    patient_age: int | None
    created_at: datetime

    @classmethod
    def from_model(cls, appointment: Appointment) -> "AppointmentDetail":
        return cls(
            id=appointment.id,
            appointment_number=appointment.appointment_number,
            token_number=appointment.token_number,
            appointment_status=appointment.appointment_status,
            booking_source=appointment.booking_source,
            clinic_id=appointment.clinic_id,
            clinic_name=appointment.clinic_name,
            clinic_address=appointment.clinic_address,
            doctor_name=appointment.doctor_name,
            consultation_fee=appointment.consultation_fee,
            appointment_date=appointment.appointment_date,
            start_time=appointment.start_time,
            end_time=appointment.end_time,
            visit_reason=appointment.visit_reason,
            doctor_notes=appointment.doctor_notes,
            patient_notes=appointment.patient_notes,
            cancellation_reason=appointment.cancellation_reason,
            patient_id=appointment.patient_id,
            patient_name=appointment.patient.full_name,
            patient_phone=appointment.patient.phone_number,
            patient_email=appointment.patient.email,
            patient_age=appointment.patient.age,
            created_at=appointment.created_at,
        )


class AppointmentUpdate(BaseModel):
    status: AppointmentStatus | None = None
    doctor_notes: str | None = Field(default=None, max_length=5000)
    cancellation_reason: str | None = Field(default=None, max_length=1000)
    reschedule_slot_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> "AppointmentUpdate":
        if self.status is None and self.doctor_notes is None and self.reschedule_slot_id is None:
            raise ValueError("Provide status, doctor_notes, or reschedule_slot_id")
        return self
