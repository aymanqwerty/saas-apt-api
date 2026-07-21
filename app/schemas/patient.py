import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.models.patient import Gender


class PatientListItem(BaseModel):
    id: uuid.UUID
    patient_code: str
    full_name: str
    phone_number: str
    email: str | None
    total_appointments: int
    last_visit: date | None


class PatientDetail(BaseModel):
    id: uuid.UUID
    patient_code: str
    full_name: str
    phone_number: str
    email: str | None
    age: int | None
    gender: Gender | None
    notes: str | None
    total_appointments: int
    last_visit: date | None
    created_at: datetime
