import uuid
from datetime import date, time

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.availability_rule import AvailabilityRuleStatus, Weekday


class AvailabilityRuleCreate(BaseModel):
    clinic_id: uuid.UUID
    weekday: Weekday
    start_time: time
    end_time: time
    slot_duration_minutes: int = Field(gt=0, le=480)
    patients_per_slot: int = Field(ge=1, le=100)
    buffer_minutes: int = Field(default=0, ge=0, le=240)
    effective_from: date
    effective_until: date | None = None
    status: AvailabilityRuleStatus = AvailabilityRuleStatus.ACTIVE

    @model_validator(mode="after")
    def _validate_times(self) -> "AvailabilityRuleCreate":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        if self.effective_until and self.effective_until < self.effective_from:
            raise ValueError("effective_until must not be before effective_from")
        return self


class AvailabilityRuleBulkCreate(BaseModel):
    """Create the same rule across several weekdays in one request."""

    clinic_id: uuid.UUID
    weekdays: list[Weekday] = Field(min_length=1)
    start_time: time
    end_time: time
    slot_duration_minutes: int = Field(gt=0, le=480)
    patients_per_slot: int = Field(ge=1, le=100)
    buffer_minutes: int = Field(default=0, ge=0, le=240)
    effective_from: date
    effective_until: date | None = None
    status: AvailabilityRuleStatus = AvailabilityRuleStatus.ACTIVE

    @model_validator(mode="after")
    def _validate(self) -> "AvailabilityRuleBulkCreate":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        if self.effective_until and self.effective_until < self.effective_from:
            raise ValueError("effective_until must not be before effective_from")
        # De-duplicate while preserving order.
        self.weekdays = list(dict.fromkeys(self.weekdays))
        return self


class AvailabilityRuleUpdate(BaseModel):
    clinic_id: uuid.UUID | None = None
    weekday: Weekday | None = None
    start_time: time | None = None
    end_time: time | None = None
    slot_duration_minutes: int | None = Field(default=None, gt=0, le=480)
    patients_per_slot: int | None = Field(default=None, ge=1, le=100)
    buffer_minutes: int | None = Field(default=None, ge=0, le=240)
    effective_from: date | None = None
    effective_until: date | None = None
    status: AvailabilityRuleStatus | None = None


class AvailabilityRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clinic_id: uuid.UUID
    weekday: Weekday
    start_time: time
    end_time: time
    slot_duration_minutes: int
    patients_per_slot: int
    buffer_minutes: int
    effective_from: date
    effective_until: date | None
    status: AvailabilityRuleStatus
    # Upcoming slots with at least one booking (shown before deleting a rule).
    upcoming_booked_count: int = 0
