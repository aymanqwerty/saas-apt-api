import uuid

from pydantic import BaseModel, Field, field_validator

from app.schemas.patient_account import PatientProfile


def _clean_phone(value: str) -> str:
    return value.strip()


class RequestOtpRequest(BaseModel):
    doctor_slug: str = Field(min_length=1)
    phone_number: str = Field(min_length=7, max_length=20)

    _normalize = field_validator("phone_number")(_clean_phone)


class RequestOtpResponse(BaseModel):
    expires_in_seconds: int
    # Only populated in development so the flow can be tested without an SMS
    # provider; None in every other environment.
    debug_code: str | None = None


class VerifyOtpRequest(BaseModel):
    doctor_slug: str = Field(min_length=1)
    phone_number: str = Field(min_length=7, max_length=20)
    code: str = Field(min_length=4, max_length=10)

    _normalize = field_validator("phone_number")(_clean_phone)


class PasswordLoginRequest(BaseModel):
    doctor_slug: str = Field(min_length=1)
    phone_number: str = Field(min_length=7, max_length=20)
    password: str = Field(min_length=1)

    _normalize = field_validator("phone_number")(_clean_phone)


class SetPasswordRequest(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class AccountSummary(BaseModel):
    id: uuid.UUID
    doctor_slug: str
    phone_number: str
    is_verified: bool
    has_password: bool
    profile_complete: bool


class PatientAuthData(BaseModel):
    token: str
    account: AccountSummary
    profile: PatientProfile | None = None
    is_new: bool = False


class MeResponse(BaseModel):
    account: AccountSummary
    profile: PatientProfile | None = None
