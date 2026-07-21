import uuid
from datetime import date, datetime, time

from pydantic import BaseModel

from app.models.patient import Gender


class BookingSessionPublic(BaseModel):
    """A review draft, returned to the website so it can pre-fill the wizard."""

    token: str
    doctor_slug: str
    clinic_id: uuid.UUID | None
    clinic_name: str | None
    slot_id: uuid.UUID | None
    slot_date: date | None
    start_time: time | None
    end_time: time | None
    name: str
    phone_number: str
    email: str | None
    age: int | None
    gender: Gender | None
    reason: str | None
    expires_at: datetime
