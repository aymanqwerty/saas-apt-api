import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.core.exceptions import ApiException
from app.models.slot import Slot, SlotStatus
from app.repositories.slot_repository import SlotRepository
from app.schemas.slot import SlotUpdate


class SlotService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._slots = SlotRepository(db)

    def list_slots(
        self,
        doctor_id: uuid.UUID,
        clinic_id: uuid.UUID | None = None,
        slot_date: date | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        status: SlotStatus | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[Slot], int]:
        return self._slots.list_for_doctor_paginated(
            doctor_id,
            clinic_id=clinic_id,
            slot_date=slot_date,
            date_from=date_from,
            date_to=date_to,
            status=status,
            page=page,
            limit=limit,
        )

    def update_slot(self, doctor_id: uuid.UUID, slot_id: uuid.UUID, data: SlotUpdate) -> Slot:
        slot = self._slots.get_for_doctor(doctor_id, slot_id)
        if slot is None:
            raise ApiException(404, "Slot not found", "NOT_FOUND")

        if data.capacity is not None:
            if data.capacity < slot.booked_count:
                raise ApiException(
                    422,
                    "Capacity cannot be less than the number of existing bookings",
                    "CAPACITY_BELOW_BOOKED",
                )
            slot.capacity = data.capacity

        if data.is_blocked is not None:
            slot.is_manually_blocked = data.is_blocked
            slot.block_reason = data.block_reason if data.is_blocked else None

        # Recompute derived status (booking/appointments arrive in Milestone 6).
        if slot.is_manually_blocked:
            slot.status = SlotStatus.BLOCKED
        elif slot.booked_count >= slot.capacity:
            slot.status = SlotStatus.FULL
        elif slot.status in (SlotStatus.BLOCKED, SlotStatus.FULL):
            slot.status = SlotStatus.AVAILABLE

        self._db.commit()
        self._db.refresh(slot)
        return slot
