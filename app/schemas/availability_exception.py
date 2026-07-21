import uuid
from datetime import date, time

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.availability_exception import ExceptionType


class AvailabilityExceptionCreate(BaseModel):
    clinic_id: uuid.UUID | None = None
    exception_date: date
    exception_type: ExceptionType
    is_available: bool
    custom_start_time: time | None = None
    custom_end_time: time | None = None
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _validate(self) -> "AvailabilityExceptionCreate":
        if self.is_available:
            if not self.custom_start_time or not self.custom_end_time:
                raise ValueError(
                    "custom_start_time and custom_end_time are required when is_available is true"
                )
            if self.custom_end_time <= self.custom_start_time:
                raise ValueError("custom_end_time must be after custom_start_time")
        return self


class AvailabilityExceptionUpdate(BaseModel):
    clinic_id: uuid.UUID | None = None
    exception_date: date | None = None
    exception_type: ExceptionType | None = None
    is_available: bool | None = None
    custom_start_time: time | None = None
    custom_end_time: time | None = None
    reason: str | None = Field(default=None, max_length=500)


class AvailabilityExceptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clinic_id: uuid.UUID | None
    exception_date: date
    exception_type: ExceptionType
    is_available: bool
    custom_start_time: time | None
    custom_end_time: time | None
    reason: str | None
