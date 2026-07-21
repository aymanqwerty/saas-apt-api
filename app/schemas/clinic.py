import uuid
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.clinic import ClinicStatus


def _validate_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("Invalid IANA timezone name") from None
    return value


class ClinicCreate(BaseModel):
    clinic_name: str = Field(min_length=1, max_length=200)
    address_line_1: str = Field(min_length=1, max_length=255)
    address_line_2: str | None = Field(default=None, max_length=255)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=1, max_length=100)
    country: str = Field(default="India", min_length=1, max_length=100)
    postal_code: str | None = Field(default=None, max_length=15)
    google_maps_url: str | None = None
    phone_number: str | None = Field(default=None, max_length=20)
    consultation_fee: Decimal | None = Field(default=None, ge=0)
    timezone: str = "Asia/Kolkata"
    description: str | None = Field(default=None, max_length=2000)
    status: ClinicStatus = ClinicStatus.ACTIVE

    _check_timezone = field_validator("timezone")(_validate_timezone)


class ClinicUpdate(BaseModel):
    clinic_name: str | None = Field(default=None, min_length=1, max_length=200)
    address_line_1: str | None = Field(default=None, min_length=1, max_length=255)
    address_line_2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    state: str | None = Field(default=None, min_length=1, max_length=100)
    country: str | None = Field(default=None, min_length=1, max_length=100)
    postal_code: str | None = Field(default=None, max_length=15)
    google_maps_url: str | None = None
    phone_number: str | None = Field(default=None, max_length=20)
    consultation_fee: Decimal | None = Field(default=None, ge=0)
    timezone: str | None = None
    description: str | None = Field(default=None, max_length=2000)
    status: ClinicStatus | None = None

    @field_validator("timezone")
    @classmethod
    def _check_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_timezone(value)


class ClinicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clinic_name: str
    address_line_1: str
    address_line_2: str | None
    city: str
    state: str
    country: str
    postal_code: str | None
    google_maps_url: str | None
    phone_number: str | None
    consultation_fee: Decimal | None
    timezone: str
    description: str | None
    status: ClinicStatus
