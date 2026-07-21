import uuid
from datetime import date

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.slot import Slot, SlotStatus


class SlotRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_for_doctor(self, doctor_id: uuid.UUID, slot_id: uuid.UUID) -> Slot | None:
        stmt = select(Slot).where(Slot.id == slot_id, Slot.doctor_id == doctor_id)
        return self._db.scalar(stmt)

    def list_for_doctor(
        self,
        doctor_id: uuid.UUID,
        clinic_id: uuid.UUID | None = None,
        slot_date: date | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        status: SlotStatus | None = None,
    ) -> list[Slot]:
        stmt = select(Slot).where(Slot.doctor_id == doctor_id)
        if clinic_id:
            stmt = stmt.where(Slot.clinic_id == clinic_id)
        if slot_date:
            stmt = stmt.where(Slot.slot_date == slot_date)
        if date_from:
            stmt = stmt.where(Slot.slot_date >= date_from)
        if date_to:
            stmt = stmt.where(Slot.slot_date <= date_to)
        if status:
            stmt = stmt.where(Slot.status == status)
        stmt = stmt.order_by(Slot.slot_date, Slot.start_time)
        return list(self._db.scalars(stmt))

    def list_for_doctor_paginated(
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
        from sqlalchemy import func

        stmt = select(Slot).where(Slot.doctor_id == doctor_id)
        if clinic_id:
            stmt = stmt.where(Slot.clinic_id == clinic_id)
        if slot_date:
            stmt = stmt.where(Slot.slot_date == slot_date)
        if date_from:
            stmt = stmt.where(Slot.slot_date >= date_from)
        if date_to:
            stmt = stmt.where(Slot.slot_date <= date_to)
        if status:
            stmt = stmt.where(Slot.status == status)

        total = self._db.scalar(select(func.count()).select_from(stmt.subquery()))
        stmt = stmt.order_by(Slot.slot_date.asc(), Slot.start_time.asc())
        items = list(self._db.scalars(stmt.offset((page - 1) * limit).limit(limit)))
        return items, total or 0

    def count_future_booked_for_rule(self, rule_id: uuid.UUID, from_date: date) -> int:
        from sqlalchemy import func

        return (
            self._db.scalar(
                select(func.count())
                .select_from(Slot)
                .where(
                    Slot.availability_rule_id == rule_id,
                    Slot.slot_date >= from_date,
                    Slot.booked_count > 0,
                )
            )
            or 0
        )

    def list_for_rule_from(self, rule_id: uuid.UUID, from_date: date) -> list[Slot]:
        stmt = select(Slot).where(
            Slot.availability_rule_id == rule_id,
            Slot.slot_date >= from_date,
        )
        return list(self._db.scalars(stmt))

    def existing_start_times(self, clinic_id: uuid.UUID, slot_date: date) -> set:
        stmt = select(Slot.start_time).where(
            Slot.clinic_id == clinic_id,
            Slot.slot_date == slot_date,
        )
        return set(self._db.scalars(stmt))

    def list_available_dates(
        self, clinic_id: uuid.UUID, from_date: date, to_date: date
    ) -> list[date]:
        """Distinct dates within the range that have at least one bookable slot."""
        stmt = (
            select(Slot.slot_date)
            .where(
                Slot.clinic_id == clinic_id,
                Slot.slot_date >= from_date,
                Slot.slot_date <= to_date,
                Slot.status == SlotStatus.AVAILABLE,
                Slot.booked_count < Slot.capacity,
            )
            .distinct()
            .order_by(Slot.slot_date)
        )
        return list(self._db.scalars(stmt))

    def list_public_for_date(self, clinic_id: uuid.UUID, slot_date: date) -> list[Slot]:
        """All bookable-in-principle slots for a date (open OR full), for the
        public booking grid. Manually blocked / expired slots are excluded."""
        stmt = (
            select(Slot)
            .where(
                Slot.clinic_id == clinic_id,
                Slot.slot_date == slot_date,
                Slot.status.in_([SlotStatus.AVAILABLE, SlotStatus.FULL]),
            )
            .order_by(Slot.start_time)
        )
        return list(self._db.scalars(stmt))

    def claim_capacity(self, slot_id: uuid.UUID) -> bool:
        """Atomically reserve one seat. Returns False if full/unavailable.

        The WHERE guard makes the read-and-increment a single statement so
        concurrent bookings can never exceed capacity (docs/03 §8).
        """
        result = self._db.execute(
            update(Slot)
            .where(
                Slot.id == slot_id,
                Slot.status == SlotStatus.AVAILABLE,
                Slot.booked_count < Slot.capacity,
            )
            .values(booked_count=Slot.booked_count + 1)
        )
        return result.rowcount == 1

    def mark_full_if_reached(self, slot_id: uuid.UUID) -> None:
        self._db.execute(
            update(Slot)
            .where(Slot.id == slot_id, Slot.booked_count >= Slot.capacity)
            .values(status=SlotStatus.FULL)
        )

    def release_capacity(self, slot_id: uuid.UUID) -> None:
        """Free one seat (on cancel/reschedule-away) and reopen a full slot."""
        self._db.execute(
            update(Slot)
            .where(Slot.id == slot_id, Slot.booked_count > 0)
            .values(booked_count=Slot.booked_count - 1)
        )
        # A slot that was FULL becomes AVAILABLE again unless manually blocked.
        self._db.execute(
            update(Slot)
            .where(
                Slot.id == slot_id,
                Slot.status == SlotStatus.FULL,
                Slot.booked_count < Slot.capacity,
                Slot.is_manually_blocked.is_(False),
            )
            .values(status=SlotStatus.AVAILABLE)
        )

    def add(self, slot: Slot) -> None:
        self._db.add(slot)

    def delete(self, slot: Slot) -> None:
        self._db.delete(slot)
