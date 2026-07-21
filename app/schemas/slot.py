import uuid
from datetime import date, time

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.slot import SlotStatus


class SlotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clinic_id: uuid.UUID
    slot_date: date
    start_time: time
    end_time: time
    capacity: int
    booked_count: int
    status: SlotStatus
    is_manually_blocked: bool
    block_reason: str | None


class SlotUpdate(BaseModel):
    """Doctor slot management: block/unblock and capacity edits (docs/05 §8)."""

    is_blocked: bool | None = None
    block_reason: str | None = Field(default=None, max_length=500)
    capacity: int | None = Field(default=None, ge=1, le=100)

    @model_validator(mode="after")
    def _at_least_one(self) -> "SlotUpdate":
        if self.is_blocked is None and self.capacity is None:
            raise ValueError("Provide is_blocked and/or capacity")
        return self
