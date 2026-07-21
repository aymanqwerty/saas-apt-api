import uuid
from datetime import date, time
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.appointment import AppointmentStatus
from app.models.patient import Gender, PatientRelationship


class ProfileUpsertRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    email: EmailStr | None = None
    gender: Gender | None = None
    date_of_birth: date | None = None
    age: int | None = Field(default=None, ge=0, le=150)


class MemberCreateRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    relationship: PatientRelationship
    phone_number: str | None = Field(default=None, max_length=20)
    email: EmailStr | None = None
    gender: Gender | None = None
    date_of_birth: date | None = None
    age: int | None = Field(default=None, ge=0, le=150)


class MemberUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=150)
    relationship: PatientRelationship | None = None
    phone_number: str | None = Field(default=None, max_length=20)
    email: EmailStr | None = None
    gender: Gender | None = None
    date_of_birth: date | None = None
    age: int | None = Field(default=None, ge=0, le=150)


class PatientProfile(BaseModel):
    """A bookable person on an account — the account holder (SELF) or a member."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    phone_number: str
    email: str | None
    gender: Gender | None
    date_of_birth: date | None
    age: int | None
    relationship: PatientRelationship | None


class MyAppointmentItem(BaseModel):
    id: uuid.UUID
    appointment_number: str
    token_number: int
    appointment_status: AppointmentStatus
    patient_id: uuid.UUID
    patient_name: str
    doctor_name: str
    clinic_name: str
    clinic_address: str
    consultation_fee: Decimal | None
    appointment_date: date
    start_time: time
    end_time: time
