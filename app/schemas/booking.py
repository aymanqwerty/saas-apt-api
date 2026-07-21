import uuid
from datetime import date, time
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.appointment import AppointmentStatus
from app.models.patient import Gender, PatientRelationship


class BookingRequest(BaseModel):
    doctor_slug: str = Field(min_length=1)
    slot_id: uuid.UUID
    # Identity fields are used for guest bookings AND for a logged-in patient
    # who types in a one-off person ("someone else"). For a saved profile the
    # booking is made for `account_member_id` and these fields are ignored.
    name: str = Field(default="", max_length=150)
    phone_number: str = Field(default="", max_length=20)
    email: EmailStr | None = None
    age: int | None = Field(default=None, ge=0, le=150)
    gender: Gender | None = None
    account_member_id: uuid.UUID | None = None
    # When a logged-in patient enters details manually, optionally keep the
    # person as a family member for next time (relationship is then required).
    save_as_member: bool = False
    relationship: PatientRelationship | None = None
    reason: str | None = Field(default=None, max_length=1000)


class BookingConfirmation(BaseModel):
    """Returned to the patient after a successful booking."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    appointment_number: str
    token_number: int
    appointment_status: AppointmentStatus
    doctor_name: str
    clinic_name: str
    clinic_address: str
    consultation_fee: Decimal | None
    appointment_date: date
    start_time: time
    end_time: time


class PaymentOrderInfo(BaseModel):
    """Everything the client needs to open the gateway checkout."""

    provider: str
    order_id: str
    amount: int  # smallest currency unit (paise)
    currency: str
    key_id: str
    display_amount: Decimal  # major units, for showing the patient
    doctor_name: str
    clinic_name: str


class BookingStartResponse(BaseModel):
    """Result of starting a booking: either confirmed (free) or awaiting payment."""

    status: Literal["confirmed", "payment_required"]
    hold_id: uuid.UUID | None = None
    appointment: BookingConfirmation | None = None
    payment: PaymentOrderInfo | None = None


class ConfirmPaymentRequest(BaseModel):
    """Provider-neutral payment proof returned by the client after checkout."""

    order_id: str = Field(min_length=1)
    payment_id: str = Field(min_length=1)
    signature: str = Field(min_length=1)
