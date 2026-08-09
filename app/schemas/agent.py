import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.patient import Gender, PatientRelationship
from app.schemas.booking import BookingConfirmation


class AgentClinic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clinic_name: str
    address: str
    consultation_fee: Decimal | None


class AgentPatient(BaseModel):
    name: str
    phone_number: str
    age: int | None
    gender: Gender | None
    email: str | None


class AgentMember(BaseModel):
    id: uuid.UUID
    name: str
    relationship: PatientRelationship | None
    age: int | None
    gender: Gender | None


class AgentPatientLookup(BaseModel):
    found: bool
    patient: AgentPatient | None = None
    members: list[AgentMember] = []


class PhoneLookupRequest(BaseModel):
    phone_number: str = Field(min_length=7, max_length=20)


class AgentBookingInput(BaseModel):
    """What the voice agent actually sends.

    Every identifier is a plain string, and each has a human-readable fallback,
    because an LLM routinely mangles or invents a UUID. `AgentService` resolves
    this into the strict `AgentBookingRequest` below, raising errors that tell
    the agent exactly which value to use instead.
    """

    clinic_id: str | None = None  # id from list_clinics, or the clinic name
    slot_id: str | None = None  # id from get_slots
    slot_date: str | None = None  # with start_time, an alternative to slot_id
    start_time: str | None = None  # "10:30", "10:30:00" or "10:30 AM"
    name: str = Field(min_length=1, max_length=150)
    phone_number: str = Field(min_length=7, max_length=20)
    email: EmailStr | None = None
    age: int | None = Field(default=None, ge=0, le=150)
    gender: Gender | None = None
    account_member_id: str | None = None
    mode: Literal["direct", "review"] = "direct"
    reason: str | None = Field(default=None, max_length=1000)


class AgentBookingRequest(BaseModel):
    clinic_id: uuid.UUID
    slot_id: uuid.UUID
    name: str = Field(min_length=1, max_length=150)
    phone_number: str = Field(min_length=7, max_length=20)
    email: EmailStr | None = None
    age: int | None = Field(default=None, ge=0, le=150)
    gender: Gender | None = None
    account_member_id: uuid.UUID | None = None
    # "direct": book/pay now (link or free confirm). "review": send a pre-filled
    # link for the patient to review and complete on the website.
    mode: Literal["direct", "review"] = "direct"
    reason: str | None = Field(default=None, max_length=1000)


class AgentBookingResult(BaseModel):
    # confirmed = booked immediately (free); payment_link = pay link sent;
    # review = review link sent.
    status: Literal["confirmed", "payment_link", "review"]
    message: str  # a natural sentence the agent can read back to the caller
    appointment: BookingConfirmation | None = None
    hold_id: uuid.UUID | None = None
    payment_link_url: str | None = None
    review_url: str | None = None
    expires_in_seconds: int | None = None
